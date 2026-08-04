"""
Structured output schema for grounded RAG answers.

Every claim carries its own citations rather than the answer carrying one
list: per-claim attribution is what makes it possible to strip an
individual fabricated statement while keeping the rest of a useful answer.
"""
from pydantic import BaseModel, Field


class Claim(BaseModel):
    text: str = Field(min_length=1)
    # Required by the schema, though the validator also recovers inline [n]
    # citations — models routinely ignore structured fields they were asked
    # to fill, and discarding otherwise-grounded claims over formatting
    # would be the wrong tradeoff.
    source_ids: list[int] = Field(default_factory=list)


class GroundedAnswer(BaseModel):
    answer: str = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list)
    # The model's own signal that the sources don't answer the question.
    # Making this an explicit field gives "I can't tell" a first-class
    # representation rather than leaving it to be inferred from prose.
    insufficient_evidence: bool = False
