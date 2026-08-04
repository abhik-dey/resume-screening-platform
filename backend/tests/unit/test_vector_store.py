"""Tests for the in-memory vector store and cosine similarity."""
import uuid

import pytest

from app.infrastructure.vector_store.in_memory_vector_store import (
    InMemoryVectorStore,
    cosine_similarity,
)


def test_cosine_similarity_of_identical_vectors_is_one():
    v = [0.6, 0.8, 0.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_of_orthogonal_vectors_is_zero():
    assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9


def test_cosine_similarity_of_opposite_vectors_is_negative_one():
    assert abs(cosine_similarity([1.0, 0.0], [-1.0, 0.0]) + 1.0) < 1e-9


def test_cosine_similarity_handles_zero_vectors():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_similarity_rejects_dimension_mismatch():
    # Silently comparing mismatched vectors would produce meaningless
    # scores that look plausible — better to fail loudly.
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


async def test_upsert_then_search_finds_the_vector():
    store = InMemoryVectorStore()
    entity_id = uuid.uuid4()
    await store.ensure_collection("test", 3)
    await store.upsert("test", entity_id, [1.0, 0.0, 0.0], {"kind": "resume"})

    results = await store.search("test", [1.0, 0.0, 0.0])
    assert len(results) == 1
    assert results[0].entity_id == entity_id
    assert results[0].payload["kind"] == "resume"


async def test_upsert_replaces_rather_than_duplicates():
    # Re-indexing a resume after re-parsing must not leave two vectors.
    store = InMemoryVectorStore()
    entity_id = uuid.uuid4()
    await store.upsert("test", entity_id, [1.0, 0.0], {"version": 1})
    await store.upsert("test", entity_id, [0.0, 1.0], {"version": 2})

    results = await store.search("test", [0.0, 1.0])
    assert len(results) == 1
    assert results[0].payload["version"] == 2


async def test_results_are_ordered_by_similarity():
    store = InMemoryVectorStore()
    exact, close, far = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await store.upsert("test", far, [0.0, 1.0], {})
    await store.upsert("test", exact, [1.0, 0.0], {})
    await store.upsert("test", close, [0.9, 0.436], {})

    results = await store.search("test", [1.0, 0.0])
    assert [r.entity_id for r in results] == [exact, close, far]


async def test_limit_is_respected():
    store = InMemoryVectorStore()
    for _ in range(10):
        await store.upsert("test", uuid.uuid4(), [1.0, 0.0], {})
    assert len(await store.search("test", [1.0, 0.0], limit=3)) == 3


async def test_filters_restrict_results_by_payload():
    # The filtered-search capability that motivated choosing Qdrant.
    store = InMemoryVectorStore()
    job_a, job_b = str(uuid.uuid4()), str(uuid.uuid4())
    await store.upsert("test", uuid.uuid4(), [1.0, 0.0], {"job_id": job_a})
    await store.upsert("test", uuid.uuid4(), [1.0, 0.0], {"job_id": job_b})

    results = await store.search("test", [1.0, 0.0], filters={"job_id": job_a})
    assert len(results) == 1
    assert results[0].payload["job_id"] == job_a


async def test_delete_removes_the_vector():
    store = InMemoryVectorStore()
    entity_id = uuid.uuid4()
    await store.upsert("test", entity_id, [1.0, 0.0], {})
    await store.delete("test", entity_id)
    assert await store.search("test", [1.0, 0.0]) == []


async def test_delete_is_idempotent():
    store = InMemoryVectorStore()
    await store.delete("nonexistent", uuid.uuid4())  # must not raise


async def test_search_on_empty_collection_returns_nothing():
    store = InMemoryVectorStore()
    assert await store.search("empty", [1.0, 0.0]) == []


async def test_ensure_collection_is_idempotent():
    store = InMemoryVectorStore()
    entity_id = uuid.uuid4()
    await store.ensure_collection("test", 2)
    await store.upsert("test", entity_id, [1.0, 0.0], {})
    await store.ensure_collection("test", 2)  # must not wipe existing data
    assert len(await store.search("test", [1.0, 0.0])) == 1


async def test_tied_scores_order_deterministically():
    store = InMemoryVectorStore()
    ids = sorted([uuid.uuid4() for _ in range(5)], key=str)
    for entity_id in reversed(ids):
        await store.upsert("test", entity_id, [1.0, 0.0], {})

    first = [r.entity_id for r in await store.search("test", [1.0, 0.0])]
    second = [r.entity_id for r in await store.search("test", [1.0, 0.0])]
    assert first == second == ids
