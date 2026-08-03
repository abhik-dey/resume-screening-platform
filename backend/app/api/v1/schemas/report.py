"""Pydantic schemas for the report endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReportResponse(BaseModel):
    id: UUID
    job_id: UUID
    generated_by: UUID
    summary: str | None
    created_at: datetime

    # Note: file_path is deliberately omitted, same as resumes in Phase 5 —
    # it's an internal storage detail. Use the download endpoint instead.
    model_config = {"from_attributes": True}


class ReportGenerationResult(BaseModel):
    """Response for POST /jobs/{id}/report."""

    success: bool
    reasoning: str
    report: ReportResponse | None
    total_candidates: int
    average_score: float
    recommendation_counts: dict[str, int]
    summary_generation_failed: bool
