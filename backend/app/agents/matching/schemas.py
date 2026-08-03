"""
Structured output schema for the Matching Agent's LLM call.

Note what is NOT here: any numeric score. The LLM contributes qualitative
prose only — the score is computed deterministically in
domain/matching/scorer.py. Keeping the score out of this schema makes it
structurally impossible for the LLM to influence the number.
"""
from pydantic import BaseModel, Field


class QualitativeAnalysis(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
