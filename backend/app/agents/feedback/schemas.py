"""
Structured output schema for the Feedback Agent's LLM call.

Note what is absent: any recommendation field. The recommendation category
is derived arithmetically in domain/feedback/recommendation.py, and keeping
it out of this schema makes it structurally impossible for the LLM to
produce or override one — the constraint is enforced by type, not by
hoping the prompt is persuasive enough.
"""
from pydantic import BaseModel, Field


class FeedbackNarrative(BaseModel):
    summary: str = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    # Job-relevant, evidence-based observations only. See the prompt's
    # explicit constraints on what may and may not appear here.
    risk_factors: list[str] = Field(default_factory=list)
    # Candidate-facing and constructive — these may be shared with the
    # applicant, so they're framed as development advice.
    improvement_suggestions: list[str] = Field(default_factory=list)
