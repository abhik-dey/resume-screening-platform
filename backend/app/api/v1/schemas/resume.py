"""
Pydantic schemas for the resume API.

Note: ResumeResponse deliberately omits `storage_path` — that's an internal
filesystem/object-store detail, not something API consumers should see or
depend on (and leaking it would be an unnecessary information disclosure).
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.entities.resume import ResumeStatus


class ResumeResponse(BaseModel):
    id: UUID
    job_id: UUID
    candidate_id: UUID | None
    original_filename: str
    status: ResumeStatus
    parsed_data: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ResumeParseResult(BaseModel):
    """Response for POST /resumes/{id}/parse — includes the agent's reasoning
    (Phase 1's traceability requirement), not just the updated resume."""

    resume: ResumeResponse
    success: bool
    reasoning: str
