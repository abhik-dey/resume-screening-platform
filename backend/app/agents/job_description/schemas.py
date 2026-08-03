"""
Structured output schema for the Job Description Agent's LLM call.

Mirrors the shape of the `jobs` table's requirement columns, but kept
separate from the Job domain entity deliberately — this describes what we
ask the LLM to extract, not how a job is persisted. Whether an extracted
value is actually applied to the job is a separate merge-policy decision
(see agent.py).
"""
from pydantic import BaseModel, Field


class JobRequirementsOutput(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_experience_years: int | None = None
    education_requirement: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
