"""Interview question domain entity."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class QuestionCategory(str, Enum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    PROJECT = "project"


class QuestionDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class InterviewQuestion:
    id: UUID
    resume_id: UUID
    job_id: UUID
    question: str
    category: QuestionCategory
    difficulty: QuestionDifficulty
    # Why this question was generated for THIS candidate — e.g. "probes the
    # Kubernetes gap identified during matching". Part of the traceability
    # requirement: a recruiter should know why they're asking something.
    rationale: str | None = None
    created_at: datetime | None = None
