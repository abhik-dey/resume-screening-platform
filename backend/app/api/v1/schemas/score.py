"""Pydantic schemas for the matching/score endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ScoreResponse(BaseModel):
    id: UUID
    resume_id: UUID
    job_id: UUID
    similarity_score: float
    skill_overlap: list[str]
    missing_skills: list[str]
    strengths: list[str]
    weaknesses: list[str]
    rank: int | None
    explanation: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchResultResponse(BaseModel):
    """Response for POST /resumes/{id}/match.

    `breakdown` exposes the full component-by-component computation, so a
    recruiter (or auditor) can see exactly how the score was reached
    rather than being handed an opaque number.
    """

    success: bool
    reasoning: str
    score: ScoreResponse | None
    breakdown: dict
    explanation: str
    qualitative_analysis_failed: bool
