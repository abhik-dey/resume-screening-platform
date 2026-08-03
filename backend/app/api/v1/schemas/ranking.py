"""Pydantic schemas for the ranking endpoints."""
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain.matching.scorer import ScoringWeights

# Matches the scorer's tolerance — floating-point sums rarely land exactly
# on 1.0 (0.6 + 0.25 + 0.15 == 0.9999999999999999 in IEEE 754).
_WEIGHT_SUM_TOLERANCE = 1e-6


class ScoringWeightsRequest(BaseModel):
    """Optional recruiter-supplied weights for a ranking run.

    Validated here so a bad request returns a clear 422 from FastAPI rather
    than surfacing as a generic agent failure.
    """

    skills: float = Field(ge=0.0, le=1.0)
    experience: float = Field(ge=0.0, le=1.0)
    education: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> "ScoringWeightsRequest":
        total = self.skills + self.experience + self.education
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"Weights must sum to 1.0 (got {total:.6f})")
        return self

    def to_domain(self) -> ScoringWeights:
        return ScoringWeights(
            skills=self.skills, experience=self.experience, education=self.education
        )


class RankRequest(BaseModel):
    """Body for POST /jobs/{id}/rank. Omit `weights` to rank on the scores
    already computed by the Matching Agent using default weighting."""

    weights: ScoringWeightsRequest | None = None


class RankedCandidateResponse(BaseModel):
    rank: int
    resume_id: UUID
    candidate_id: UUID | None
    similarity_score: float
    skill_overlap: list[str]
    missing_skills: list[str]
    strengths: list[str]
    weaknesses: list[str]
    explanation: str | None
    tie_break_reason: str | None = None


class RankingResult(BaseModel):
    """Response for POST /jobs/{id}/rank."""

    success: bool
    reasoning: str
    total_candidates: int
    weights_applied: dict | None
    ranking: list[RankedCandidateResponse]
