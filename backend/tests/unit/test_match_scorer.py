"""
Tests for the deterministic match scorer.

Determinism and explainability are this module's whole reason for existing,
so both are tested explicitly rather than assumed.
"""
from app.domain.matching.scorer import (
    EDUCATION_WEIGHT,
    EXPERIENCE_WEIGHT,
    SKILLS_WEIGHT,
    compute_match_score,
    education_level,
)


def _score(**overrides) -> object:
    defaults = {
        "candidate_skills": ["Python", "PostgreSQL"],
        "required_skills": ["Python", "PostgreSQL"],
        "preferred_skills": [],
        "candidate_years_experience": 5.0,
        "required_years_experience": 5,
        "candidate_education": "BSc Computer Science",
        "required_education": "Bachelor's degree",
    }
    defaults.update(overrides)
    return compute_match_score(**defaults)


def test_weights_sum_to_one():
    assert SKILLS_WEIGHT + EXPERIENCE_WEIGHT + EDUCATION_WEIGHT == 1.0


def test_perfect_match_scores_one():
    result = _score()
    assert result.overall_score == 1.0
    assert result.missing_required == []


def test_scoring_is_deterministic_across_repeated_calls():
    # The central claim of this design: identical inputs -> identical output,
    # every time. Anything else is indefensible in a hiring context.
    results = [_score().overall_score for _ in range(50)]
    assert len(set(results)) == 1


def test_no_skills_match_zeroes_the_skills_component():
    result = _score(candidate_skills=["Java"], required_skills=["Python", "Go"])
    skills = next(c for c in result.components if c.name == "skills")
    assert skills.raw_score == 0.0
    assert set(result.missing_required) == {"Python", "Go"}


def test_required_skills_weigh_more_than_preferred():
    # One required skill matched out of one required + one preferred:
    # earned = 3, total = 3 + 1 = 4 -> 0.75
    only_required = compute_match_score(
        candidate_skills=["Python"],
        required_skills=["Python"],
        preferred_skills=["Kubernetes"],
        candidate_years_experience=None,
        required_years_experience=None,
        candidate_education=None,
        required_education=None,
    )
    skills_a = next(c for c in only_required.components if c.name == "skills")
    assert skills_a.raw_score == 0.75

    # Only the preferred skill matched: earned = 1, total = 4 -> 0.25
    only_preferred = compute_match_score(
        candidate_skills=["Kubernetes"],
        required_skills=["Python"],
        preferred_skills=["Kubernetes"],
        candidate_years_experience=None,
        required_years_experience=None,
        candidate_education=None,
        required_education=None,
    )
    skills_b = next(c for c in only_preferred.components if c.name == "skills")
    assert skills_b.raw_score == 0.25
    assert skills_a.raw_score > skills_b.raw_score


def test_skill_comparison_is_case_insensitive():
    result = _score(candidate_skills=["python", "POSTGRESQL"], required_skills=["Python", "PostgreSQL"])
    assert result.missing_required == []


def test_job_with_no_requirements_scores_fully():
    result = compute_match_score(
        candidate_skills=[],
        required_skills=[],
        preferred_skills=[],
        candidate_years_experience=None,
        required_years_experience=None,
        candidate_education=None,
        required_education=None,
    )
    # Every stated requirement is met, because there are none.
    assert result.overall_score == 1.0


def test_experience_below_requirement_scores_proportionally():
    result = _score(candidate_years_experience=2.0, required_years_experience=4)
    experience = next(c for c in result.components if c.name == "experience")
    assert experience.raw_score == 0.5


def test_excess_experience_is_capped_at_one():
    modest = _score(candidate_years_experience=5.0, required_years_experience=5)
    excessive = _score(candidate_years_experience=25.0, required_years_experience=5)
    assert modest.overall_score == excessive.overall_score


def test_unknown_experience_scores_zero_when_required():
    result = _score(candidate_years_experience=None, required_years_experience=5)
    experience = next(c for c in result.components if c.name == "experience")
    assert experience.raw_score == 0.0


def test_unknown_experience_scores_full_when_not_required():
    result = _score(candidate_years_experience=None, required_years_experience=None)
    experience = next(c for c in result.components if c.name == "experience")
    assert experience.raw_score == 1.0


def test_education_level_ranking():
    assert education_level("High School Diploma") == 1
    assert education_level("Associate Degree") == 2
    assert education_level("BSc Computer Science") == 3
    assert education_level("Master of Science") == 4
    assert education_level("PhD in Machine Learning") == 5
    assert education_level(None) == 0
    assert education_level("Certificate of Attendance") == 0


def test_education_level_takes_the_highest_when_multiple_present():
    # A resume listing both degrees should count as the higher one.
    assert education_level("BSc Computer Science, MSc Data Science") == 4


def test_education_short_aliases_do_not_collide_as_substrings():
    # Regression: short aliases like "ma"/"ba"/"be" must match as whole
    # words only. "Diploma" contains "ma" and was wrongly ranked as a
    # Master's degree before word-boundary matching was introduced.
    assert education_level("High School Diploma") == 1
    assert education_level("Diploma in Web Design") == 1
    # "Bachelor" contains "ba"; must still resolve to bachelor level (3),
    # not be confused by the shorter alias.
    assert education_level("Bachelor of Arts") == 3
    # A company or field name containing an alias as a substring must not
    # register as a degree at all.
    assert education_level("Worked at Bemax Industries") == 0
    assert education_level("Studied Mathematics") == 0


def test_exceeding_education_requirement_is_capped():
    meets = _score(candidate_education="BSc", required_education="Bachelor")
    exceeds = _score(candidate_education="PhD", required_education="Bachelor")
    education_a = next(c for c in meets.components if c.name == "education")
    education_b = next(c for c in exceeds.components if c.name == "education")
    assert education_a.raw_score == education_b.raw_score == 1.0


def test_breakdown_is_fully_explainable():
    result = _score()
    breakdown = result.to_breakdown_dict()
    assert set(breakdown.keys()) >= {
        "overall_score", "components", "matched_required", "missing_required",
    }
    assert len(breakdown["components"]) == 3
    for component in breakdown["components"]:
        # Every component must carry its own arithmetic AND a human-readable
        # justification — that's what "explain every score" requires.
        assert {"name", "raw_score", "weight", "weighted_score", "detail"} <= set(component.keys())
        assert component["detail"]


def test_weighted_scores_sum_to_overall():
    result = _score(
        candidate_skills=["Python"],
        required_skills=["Python", "Go"],
        candidate_years_experience=3.0,
        required_years_experience=5,
    )
    total = sum(c.weighted_score for c in result.components)
    assert abs(total - result.overall_score) < 0.0001


def test_score_is_always_within_bounds():
    scenarios = [
        {"candidate_skills": [], "required_skills": ["Python"]},
        {"candidate_skills": ["Python"] * 50, "required_skills": ["Python"]},
        {"candidate_years_experience": 0.0, "required_years_experience": 10},
        {"candidate_years_experience": 100.0, "required_years_experience": 1},
        {"candidate_education": None, "required_education": "PhD"},
    ]
    for overrides in scenarios:
        result = _score(**overrides)
        assert 0.0 <= result.overall_score <= 1.0
