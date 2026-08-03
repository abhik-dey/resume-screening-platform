"""Pydantic schemas for the interview question endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.agents.interview_question.agent import (
    DEFAULT_QUESTION_COUNT,
    MAX_QUESTION_COUNT,
    MIN_QUESTION_COUNT,
)
from app.domain.entities.interview_question import QuestionCategory, QuestionDifficulty


class InterviewQuestionRequest(BaseModel):
    question_count: int = Field(
        default=DEFAULT_QUESTION_COUNT, ge=MIN_QUESTION_COUNT, le=MAX_QUESTION_COUNT
    )


class InterviewQuestionResponse(BaseModel):
    id: UUID
    resume_id: UUID
    job_id: UUID
    question: str
    category: QuestionCategory
    difficulty: QuestionDifficulty
    rationale: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InterviewQuestionGenerationResult(BaseModel):
    """Response for POST /resumes/{id}/interview-questions.

    `by_category` and `by_difficulty` summarize the spread so a recruiter
    can see at a glance whether the set is balanced.
    """

    success: bool
    reasoning: str
    questions: list[InterviewQuestionResponse]
    by_category: dict[str, int]
    by_difficulty: dict[str, int]
