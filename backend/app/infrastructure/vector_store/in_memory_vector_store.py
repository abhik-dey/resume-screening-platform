"""
In-memory vector store — brute-force cosine similarity.

Used by the test suite and as a zero-dependency fallback. Correctness over
speed: it scans every vector on each search, which is fine for tests and
small local datasets but obviously not for production scale. That's what
Qdrant is for.

Implements the same VectorStore interface as the Qdrant adapter, so tests
exercise real code paths rather than a mock that could drift from reality.
"""
import math
from uuid import UUID

from app.domain.interfaces.vector_store import VectorSearchResult, VectorStore


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Dimension mismatch: {len(a)} vs {len(b)}")
    # strict=True is redundant given the length check above, but being
    # explicit means a future refactor removing that check can't silently
    # start truncating to the shorter vector.
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    # Clamped: floating-point error can push a self-comparison marginally
    # above 1.0, which looks like a bug in downstream output.
    return max(-1.0, min(1.0, dot / (mag_a * mag_b)))


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._collections: dict[str, dict[UUID, tuple[list[float], dict]]] = {}
        self._dimensions: dict[str, int] = {}

    async def ensure_collection(self, name: str, dimensions: int) -> None:
        if name not in self._collections:
            self._collections[name] = {}
            self._dimensions[name] = dimensions

    async def upsert(
        self, collection: str, entity_id: UUID, vector: list[float], payload: dict
    ) -> None:
        if collection not in self._collections:
            await self.ensure_collection(collection, len(vector))
        self._collections[collection][entity_id] = (list(vector), dict(payload))

    async def search(
        self,
        collection: str,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[VectorSearchResult]:
        entries = self._collections.get(collection, {})
        results = []
        for entity_id, (stored_vector, payload) in entries.items():
            if filters and not _matches(payload, filters):
                continue
            results.append(
                VectorSearchResult(
                    entity_id=entity_id,
                    score=cosine_similarity(vector, stored_vector),
                    payload=dict(payload),
                )
            )
        # Secondary sort on id keeps ordering deterministic when scores tie —
        # same principle as the Phase 10 ranker.
        results.sort(key=lambda r: (-r.score, str(r.entity_id)))
        return results[:limit]

    async def delete(self, collection: str, entity_id: UUID) -> None:
        self._collections.get(collection, {}).pop(entity_id, None)


def _matches(payload: dict, filters: dict) -> bool:
    return all(str(payload.get(key)) == str(value) for key, value in filters.items())
