"""Structured output schema for the Report Generator's optional LLM summary."""
from pydantic import BaseModel, Field


class ExecutiveSummary(BaseModel):
    """A short narrative overview of the candidate pool.

    This is the ONLY LLM-generated content in a report. Every number, name,
    rank, and recommendation comes from the database.
    """

    summary: str = Field(min_length=1)
