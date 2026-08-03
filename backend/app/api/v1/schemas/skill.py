"""Pydantic schemas for the resume-skill endpoints."""
from uuid import UUID

from pydantic import BaseModel

from app.domain.entities.skill import SkillCategory


class ResumeSkillResponse(BaseModel):
    skill_id: UUID
    name: str
    category: SkillCategory
    confidence: float | None

    model_config = {"from_attributes": True}


class SkillExtractionResult(BaseModel):
    """Response for POST /resumes/{id}/extract-skills."""

    success: bool
    reasoning: str
    resolved_skills: list[dict]
    unresolved_raw_skills: list[str]
