"""Pydantic schemas for indexing and semantic search."""
from uuid import UUID

from pydantic import BaseModel, Field


class IndexResult(BaseModel):
    success: bool
    reasoning: str
    dimensions: int | None = None
    embedding_model: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=100)
    job_id: UUID | None = None


class SearchHit(BaseModel):
    resume_id: UUID
    job_id: UUID | None
    similarity: float
    candidate_name: str | None = None
    candidate_email: str | None = None
    original_filename: str | None = None


class SearchResponse(BaseModel):
    """Response for semantic search.

    `embedding_model` is surfaced so a caller can tell whether results came
    from a real semantic model or the deterministic local fallback — the
    latter matches on character patterns, not meaning, and results should
    be read very differently.
    """

    query: str
    embedding_model: str
    total_hits: int
    results: list[SearchHit]
