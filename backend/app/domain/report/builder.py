"""
Report data assembly — pure aggregation of already-computed results.

This module does no analysis. Every score, rank, and recommendation was
computed by an earlier agent; this just organizes them into the shape the
PDF renderer needs. Keeping assembly separate from rendering means the
data structure can be unit-tested without generating a single PDF, and a
future HTML or CSV exporter could reuse it unchanged.

Pure and I/O-free, in the same spirit as domain/matching/scorer.py.
"""
from dataclasses import dataclass, field

from app.domain.entities.candidate_feedback import CandidateFeedback
from app.domain.entities.job import Job
from app.domain.entities.score import Score
from app.domain.feedback.recommendation import RecommendationCategory

# Display labels for recommendation categories. Kept here rather than in the
# renderer so any future exporter shows identical wording.
RECOMMENDATION_LABELS: dict[RecommendationCategory, str] = {
    RecommendationCategory.STRONG_RECOMMEND: "Strong Match",
    RecommendationCategory.RECOMMEND: "Recommended",
    RecommendationCategory.CONSIDER: "Consider",
    RecommendationCategory.NOT_RECOMMENDED: "Not Recommended",
}


@dataclass
class CandidateRow:
    """One candidate's line in the report."""

    rank: int | None
    candidate_name: str
    candidate_email: str | None
    resume_filename: str
    similarity_score: float
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    recommendation_label: str | None = None
    threshold_rationale: str | None = None
    summary: str | None = None
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)


@dataclass
class ReportData:
    job_title: str
    job_description: str
    required_skills: list[str]
    preferred_skills: list[str]
    min_experience_years: int | None
    education_requirement: str | None
    candidates: list[CandidateRow] = field(default_factory=list)
    executive_summary: str | None = None
    summary_generation_failed: bool = False

    @property
    def total_candidates(self) -> int:
        return len(self.candidates)

    @property
    def average_score(self) -> float:
        if not self.candidates:
            return 0.0
        return round(sum(c.similarity_score for c in self.candidates) / len(self.candidates), 4)

    @property
    def recommendation_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for candidate in self.candidates:
            if candidate.recommendation_label:
                counts[candidate.recommendation_label] = (
                    counts.get(candidate.recommendation_label, 0) + 1
                )
        return counts


def assemble_report_data(
    job: Job,
    scores: list[Score],
    resume_filenames: dict,
    candidate_details: dict,
    feedback_by_resume: dict,
) -> ReportData:
    """Build the report's data structure from already-computed results.

    `resume_filenames`, `candidate_details`, and `feedback_by_resume` are
    keyed by resume_id. Candidates without feedback are still included —
    a report that silently omitted candidates would be misleading about how
    many people applied.

    Ordering matches the Ranking Agent: by rank, with unranked candidates
    last, then by score. Sorting deterministically here (rather than relying
    on whatever order the database returned) keeps the report reproducible.
    """
    rows: list[CandidateRow] = []
    for score in scores:
        feedback: CandidateFeedback | None = feedback_by_resume.get(score.resume_id)
        details = candidate_details.get(score.resume_id) or {}

        rows.append(
            CandidateRow(
                rank=score.rank,
                candidate_name=details.get("full_name") or "Unidentified candidate",
                candidate_email=details.get("email"),
                resume_filename=resume_filenames.get(score.resume_id, "unknown"),
                similarity_score=score.similarity_score,
                matched_skills=list(score.skill_overlap),
                missing_skills=list(score.missing_skills),
                recommendation_label=(
                    RECOMMENDATION_LABELS.get(feedback.recommendation) if feedback else None
                ),
                threshold_rationale=feedback.threshold_rationale if feedback else None,
                summary=feedback.summary if feedback else None,
                strengths=list(feedback.strengths) if feedback else [],
                weaknesses=list(feedback.weaknesses) if feedback else [],
                risk_factors=list(feedback.risk_factors) if feedback else [],
            )
        )

    # Unranked candidates sort last (rank is None until the Ranking Agent
    # runs); within each group, higher scores first, then filename for a
    # stable final tie-break.
    rows.sort(
        key=lambda r: (
            r.rank if r.rank is not None else float("inf"),
            -r.similarity_score,
            r.resume_filename,
        )
    )

    return ReportData(
        job_title=job.title,
        job_description=job.description,
        required_skills=list(job.required_skills),
        preferred_skills=list(job.preferred_skills),
        min_experience_years=job.min_experience_years,
        education_requirement=job.education_requirement,
        candidates=rows,
    )
