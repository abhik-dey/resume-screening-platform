"""Pydantic schemas for RAG question answering."""
from pydantic import BaseModel, Field

from app.services.rag_service import DEFAULT_TOP_K, MAX_TOP_K


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=MAX_TOP_K)
    job_id: str | None = None


class ClaimResponse(BaseModel):
    text: str
    source_ids: list[int]
    warning: str | None = None


class SourceResponse(BaseModel):
    """A retrieved resume excerpt, returned in full.

    The text is included deliberately: citation validation catches
    fabricated source IDs but cannot verify that a real source actually
    supports a claim. Returning the source text is what makes independent
    verification possible.
    """

    source_id: int
    resume_id: str
    candidate_name: str
    similarity: float
    text: str


class AskResponse(BaseModel):
    question: str
    answer: str
    claims: list[ClaimResponse]
    sources: list[SourceResponse]
    insufficient_evidence: bool
    # Records what citation validation stripped and why — visible rather
    # than silently discarded, so a pattern of fabrication is noticeable.
    citation_warnings: list[str]
    answer_rejected: bool
