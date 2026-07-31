"""Job posting domain entity."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class JobStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


@dataclass
class Job:
    id: UUID
    created_by: UUID
    title: str
    description: str
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    min_experience_years: int | None = None
    education_requirement: str | None = None
    responsibilities: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    status: JobStatus = JobStatus.DRAFT
    created_at: datetime | None = None
