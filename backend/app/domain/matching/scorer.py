"""
Match scoring — pure, deterministic, and fully explainable.

The numeric score NEVER comes from an LLM. This is a deliberate design
decision for a hiring context:

  - Reproducible: the same inputs always produce the same score, so a
    candidate or auditor asking "why 0.72?" gets a stable, checkable answer.
  - Explainable: every point is traceable to a specific component with a
    named weight, rather than "the model decided."
  - Tunable: weights are named constants, so recruiter-specific weighting
    (Phase 10) is a parameter change, not a prompt-engineering exercise.

The LLM's role in matching is qualitative only (strengths/weaknesses prose)
— see agents/matching/agent.py.

This module is I/O-free and framework-free, same as domain/validation and
domain/skills, so it is fully unit-testable in isolation.
"""
import re
from dataclasses import dataclass, field

# --- Default component weights (must sum to 1.0) ---
# Exposed as module constants for backwards compatibility and as the
# defaults of ScoringWeights below. Phase 10 allows recruiters to override
# these per ranking run, so nothing here is hardcoded into the algorithm.
SKILLS_WEIGHT = 0.60
EXPERIENCE_WEIGHT = 0.25
EDUCATION_WEIGHT = 0.15

# A required skill counts this many times more than a preferred one when
# computing the skills component.
REQUIRED_SKILL_MULTIPLIER = 3.0

# Floating-point sums rarely land exactly on 1.0 (0.6 + 0.25 + 0.15 is
# 0.9999999999999999 in IEEE 754), so weight validation uses a tolerance
# rather than exact equality.
_WEIGHT_SUM_TOLERANCE = 1e-6


class InvalidWeightsError(ValueError):
    """Raised when custom scoring weights are negative or don't sum to 1.0."""


@dataclass(frozen=True)
class ScoringWeights:
    """Component weights for match scoring.

    Frozen so a weights object can't be mutated after validation — a
    half-modified weights object producing scores that don't sum correctly
    would be a subtle and hard-to-trace bug.
    """

    skills: float = SKILLS_WEIGHT
    experience: float = EXPERIENCE_WEIGHT
    education: float = EDUCATION_WEIGHT

    def __post_init__(self) -> None:
        for name, value in (
            ("skills", self.skills),
            ("experience", self.experience),
            ("education", self.education),
        ):
            if value < 0:
                raise InvalidWeightsError(f"Weight '{name}' cannot be negative (got {value})")
        total = self.skills + self.experience + self.education
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise InvalidWeightsError(
                f"Weights must sum to 1.0 (got {total:.6f}: skills={self.skills}, "
                f"experience={self.experience}, education={self.education})"
            )


DEFAULT_WEIGHTS = ScoringWeights()

# Education levels ranked lowest to highest. Matched with WORD BOUNDARIES,
# not naive substring containment: short aliases like "ma", "ba", "be" would
# otherwise collide with unrelated words ("Diploma" contains "ma", which
# would wrongly rank a high-school diploma as a Master's degree). Kept
# deliberately simple and predictable rather than clever, since an
# unpredictable education heuristic is worse than a transparent one.
_EDUCATION_LEVELS: list[tuple[int, tuple[str, ...]]] = [
    (1, ("high school", "secondary", "diploma", "hsc", "ssc")),
    (2, ("associate",)),
    (
        3,
        (
            "bachelor", "bachelors", "bsc", "b.sc", "b.s.", "be", "b.e",
            "btech", "b.tech", "ba", "undergraduate",
        ),
    ),
    (4, ("master", "masters", "msc", "m.sc", "m.s.", "mtech", "m.tech", "ma", "mba", "postgraduate")),
    (5, ("phd", "ph.d", "doctorate", "doctoral")),
]


@dataclass
class ComponentScore:
    """One weighted component of the overall score, with its inputs visible."""

    name: str
    raw_score: float  # 0.0-1.0 before weighting
    weight: float
    weighted_score: float
    detail: str


@dataclass
class MatchResult:
    overall_score: float  # 0.0-1.0
    components: list[ComponentScore] = field(default_factory=list)
    matched_required: list[str] = field(default_factory=list)
    matched_preferred: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_preferred: list[str] = field(default_factory=list)

    @property
    def skill_overlap(self) -> list[str]:
        return self.matched_required + self.matched_preferred

    @property
    def missing_skills(self) -> list[str]:
        return self.missing_required + self.missing_preferred

    def to_breakdown_dict(self) -> dict:
        """Serializable breakdown for the audit log and API response —
        this is what makes the score auditable rather than opaque."""
        return {
            "overall_score": self.overall_score,
            "components": [
                {
                    "name": c.name,
                    "raw_score": c.raw_score,
                    "weight": c.weight,
                    "weighted_score": c.weighted_score,
                    "detail": c.detail,
                }
                for c in self.components
            ],
            "matched_required": self.matched_required,
            "matched_preferred": self.matched_preferred,
            "missing_required": self.missing_required,
            "missing_preferred": self.missing_preferred,
        }


def _normalize_for_comparison(skill: str) -> str:
    return skill.strip().lower()


def _score_skills(
    candidate_skills: list[str],
    required_skills: list[str],
    preferred_skills: list[str],
    weight: float,
) -> tuple[ComponentScore, list[str], list[str], list[str], list[str]]:
    """Weighted skill coverage. Required skills count REQUIRED_SKILL_MULTIPLIER
    times more than preferred ones."""
    candidate_set = {_normalize_for_comparison(s) for s in candidate_skills}

    matched_required, missing_required = [], []
    for skill in required_skills:
        if _normalize_for_comparison(skill) in candidate_set:
            matched_required.append(skill)
        else:
            missing_required.append(skill)

    matched_preferred, missing_preferred = [], []
    for skill in preferred_skills:
        if _normalize_for_comparison(skill) in candidate_set:
            matched_preferred.append(skill)
        else:
            missing_preferred.append(skill)

    total_weight = len(required_skills) * REQUIRED_SKILL_MULTIPLIER + len(preferred_skills)
    if total_weight == 0:
        # A job listing no skills at all can't discriminate on skills.
        # Scoring 1.0 (rather than 0.0) is correct: the candidate has met
        # every skill requirement that exists, which is none.
        return (
            ComponentScore(
                name="skills",
                raw_score=1.0,
                weight=weight,
                weighted_score=weight,
                detail="Job lists no skill requirements; skills component scored as fully met.",
            ),
            matched_required,
            matched_preferred,
            missing_required,
            missing_preferred,
        )

    earned = len(matched_required) * REQUIRED_SKILL_MULTIPLIER + len(matched_preferred)
    raw = earned / total_weight
    detail = (
        f"Matched {len(matched_required)}/{len(required_skills)} required and "
        f"{len(matched_preferred)}/{len(preferred_skills)} preferred skills "
        f"(required weighted {REQUIRED_SKILL_MULTIPLIER}x)."
    )
    return (
        ComponentScore(
            name="skills",
            raw_score=raw,
            weight=weight,
            weighted_score=raw * weight,
            detail=detail,
        ),
        matched_required,
        matched_preferred,
        missing_required,
        missing_preferred,
    )


def _score_experience(
    candidate_years: float | None, required_years: int | None, weight: float
) -> ComponentScore:
    if required_years is None or required_years <= 0:
        return ComponentScore(
            name="experience",
            raw_score=1.0,
            weight=weight,
            weighted_score=weight,
            detail="Job states no minimum experience; component scored as fully met.",
        )

    if candidate_years is None:
        return ComponentScore(
            name="experience",
            raw_score=0.0,
            weight=weight,
            weighted_score=0.0,
            detail=f"Job requires {required_years} years; none could be determined from the resume.",
        )

    # Capped at 1.0: exceeding the requirement doesn't earn bonus points,
    # since "more years than needed" isn't proportionally better and would
    # otherwise let a 20-year candidate dominate on a 2-year requirement.
    raw = min(candidate_years / required_years, 1.0)
    return ComponentScore(
        name="experience",
        raw_score=raw,
        weight=weight,
        weighted_score=raw * weight,
        detail=f"Candidate has ~{candidate_years:.1f} years against a {required_years}-year requirement.",
    )


def education_level(text: str | None) -> int:
    """Map free-text education to a rank (0 = none/unrecognized, 5 = doctorate).
    Returns the HIGHEST level found, since a resume listing both a BSc and an
    MSc should count as the MSc.

    Uses word-boundary matching rather than substring containment — naive
    containment made "High School Diploma" match the "ma" alias for Master's.
    """
    if not text:
        return 0
    lowered = text.lower()
    best = 0
    for level, keywords in _EDUCATION_LEVELS:
        for keyword in keywords:
            # re.escape handles the "." in aliases like "b.sc"; \b anchors
            # ensure "ma" doesn't match inside "diploma".
            if re.search(rf"\b{re.escape(keyword)}\b", lowered):
                best = max(best, level)
                break
    return best


def _score_education(
    candidate_education: str | None, required_education: str | None, weight: float
) -> ComponentScore:
    required_level = education_level(required_education)
    if required_level == 0:
        return ComponentScore(
            name="education",
            raw_score=1.0,
            weight=weight,
            weighted_score=weight,
            detail="Job states no education requirement; component scored as fully met.",
        )

    candidate_level = education_level(candidate_education)
    if candidate_level == 0:
        return ComponentScore(
            name="education",
            raw_score=0.0,
            weight=weight,
            weighted_score=0.0,
            detail=f"Job requires {required_education!r}; no education could be determined from the resume.",
        )

    raw = min(candidate_level / required_level, 1.0)
    return ComponentScore(
        name="education",
        raw_score=raw,
        weight=weight,
        weighted_score=raw * weight,
        detail=(
            f"Candidate education level {candidate_level} against required level {required_level} "
            f"({required_education!r})."
        ),
    )


def compute_match_score(
    candidate_skills: list[str],
    required_skills: list[str],
    preferred_skills: list[str],
    candidate_years_experience: float | None,
    required_years_experience: int | None,
    candidate_education: str | None,
    required_education: str | None,
    weights: ScoringWeights | None = None,
) -> MatchResult:
    """Compute a deterministic, explainable match score.

    Pure function: no I/O, no LLM, no randomness. The same arguments always
    produce the same result, which is what makes the score defensible.

    `weights` defaults to the standard 60/25/15 split. Phase 10 lets
    recruiters supply their own per ranking run — a specialist role might
    weight skills at 80%, a junior role might weight education higher.
    """
    active_weights = weights or DEFAULT_WEIGHTS

    skills_component, matched_req, matched_pref, missing_req, missing_pref = _score_skills(
        candidate_skills, required_skills, preferred_skills, active_weights.skills
    )
    experience_component = _score_experience(
        candidate_years_experience, required_years_experience, active_weights.experience
    )
    education_component = _score_education(
        candidate_education, required_education, active_weights.education
    )

    components = [skills_component, experience_component, education_component]
    overall = sum(c.weighted_score for c in components)

    return MatchResult(
        # Rounded to 4dp so the stored float is stable across serialization
        # round-trips (JSON -> DB -> JSON) rather than drifting in the last bits.
        overall_score=round(overall, 4),
        components=components,
        matched_required=matched_req,
        matched_preferred=matched_pref,
        missing_required=missing_req,
        missing_preferred=missing_pref,
    )
