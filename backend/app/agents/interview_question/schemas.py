"""Structured output schema for the Interview Question Agent's LLM call."""
from pydantic import BaseModel, Field

from app.domain.entities.interview_question import QuestionCategory, QuestionDifficulty


class GeneratedQuestion(BaseModel):
    question: str = Field(min_length=1)
    category: QuestionCategory
    difficulty: QuestionDifficulty
    # Required, not optional: every question must justify why it was chosen
    # for THIS candidate. A question with no rationale is a generic question,
    # which defeats the purpose of tailoring them.
    rationale: str = Field(min_length=1)


class InterviewQuestionSet(BaseModel):
    questions: list[GeneratedQuestion] = Field(default_factory=list)
