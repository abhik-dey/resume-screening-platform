"""Pydantic schemas for the feedback endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.feedback.recommendation import RecommendationCategory


class FeedbackResponse(BaseModel):
    id: UUID
    resume_id: UUID
    job_id: UUID
    recommendation: RecommendationCategory
    threshold_rationale: str
    summary: str | None
    strengths: list[str]
    weaknesses: list[str]
    risk_factors: list[str]
    improvement_suggestions: list[str]
    narrative_generation_failed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackGenerationResult(BaseModel):
    """Response for POST /resumes/{id}/feedback.

    `advisory_notice` is a REQUIRED field rather than an optional footnote:
    any UI consuming this API has to handle it, which is the point. This is
    the only endpoint that produces a hiring recommendation, and the framing
    that it's advisory should not be skippable.
    """

    success: bool
    reasoning: str
    feedback: FeedbackResponse | None
    advisory_notice: str
