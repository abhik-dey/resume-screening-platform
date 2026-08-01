"""Pydantic schemas for the job API."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities.job import JobStatus


class JobCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_experience_years: int | None = Field(default=None, ge=0, le=60)
    education_requirement: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    status: JobStatus = JobStatus.OPEN


class JobResponse(BaseModel):
    id: UUID
    created_by: UUID
    title: str
    description: str
    required_skills: list[str]
    preferred_skills: list[str]
    min_experience_years: int | None
    education_requirement: str | None
    responsibilities: list[str]
    keywords: list[str]
    status: JobStatus
    created_at: datetime

    model_config = {"from_attributes": True}
