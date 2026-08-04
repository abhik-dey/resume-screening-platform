"""Qdrant implementation of VectorStore."""
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.domain.interfaces.vector_store import VectorSearchResult, VectorStore


class QdrantVectorStore(VectorStore):
    def __init__(self, url: str) -> None:
        self._client = AsyncQdrantClient(url=url)

    async def ensure_collection(self, name: str, dimensions: int) -> None:
        existing = await self._client.get_collections()
        if any(c.name == name for c in existing.collections):
            return
        await self._client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=dimensions, distance=models.Distance.COSINE
            ),
        )

    async def upsert(
        self, collection: str, entity_id: UUID, vector: list[float], payload: dict
    ) -> None:
        await self._client.upsert(
            collection_name=collection,
            points=[
                models.PointStruct(id=str(entity_id), vector=vector, payload=payload)
            ],
        )

    async def search(
        self,
        collection: str,
        vector: list[float],
        limit: int = 10,
        filters: dict | None = None,
    ) -> list[VectorSearchResult]:
        query_filter = None
        if filters:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(key=key, match=models.MatchValue(value=str(value)))
                    for key, value in filters.items()
                ]
            )

        response = await self._client.query_points(
            collection_name=collection,
            query=vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            VectorSearchResult(
                entity_id=UUID(str(point.id)),
                score=float(point.score),
                payload=dict(point.payload or {}),
            )
            for point in response.points
        ]

    async def delete(self, collection: str, entity_id: UUID) -> None:
        await self._client.delete(
            collection_name=collection,
            points_selector=models.PointIdsList(points=[str(entity_id)]),
        )
