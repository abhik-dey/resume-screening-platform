"""
Abstract vector store interface.

Qdrant in production, an in-memory implementation in tests. Keeping this a
port means the test suite exercises the same interface real code uses,
without requiring a running Qdrant container.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class VectorSearchResult:
    entity_id: UUID
    score: float  # cosine similarity, 0.0-1.0 (higher is more similar)
    payload: dict = field(default_factory=dict)


class VectorStore(ABC):
    @abstractmethod
    async def ensure_collection(self, name: str, dimensions: int) -> None:
        """Create the collection if absent. Idempotent — safe to call on
        every startup."""

    @abstractmethod
    async def upsert(
        self, collection: str, entity_id: UUID, vector: list[float], payload: dict
    ) -> None:
        """Insert or replace a vector. Upsert because re-indexing a resume
        after re-parsing must replace its vector, not add a duplicate."""

    @abstractmethod
    async def search(
        self,
        collection: str,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[VectorSearchResult]:
        """Return the most similar vectors, best first.

        `filters` restricts results by payload field (e.g. only resumes for
        a given job) — this is why Qdrant was chosen over a simpler vector
        index in Phase 1: filtered search is a first-class operation."""

    @abstractmethod
    async def delete(self, collection: str, entity_id: UUID) -> None:
        """Remove a vector. Should not raise if it's already absent."""
