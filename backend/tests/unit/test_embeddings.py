"""Tests for the deterministic local embedding provider."""
import math

from app.infrastructure.embeddings.hash_embedding_provider import HashEmbeddingProvider
from app.infrastructure.vector_store.in_memory_vector_store import cosine_similarity


async def test_embeddings_are_deterministic():
    # The whole point of the local provider: identical text always produces
    # an identical vector, so tests never flake on embedding drift.
    provider = HashEmbeddingProvider()
    first = await provider.embed(["Python backend engineer"])
    second = await provider.embed(["Python backend engineer"])
    assert first == second


async def test_vectors_have_the_declared_dimensions():
    provider = HashEmbeddingProvider(dimensions=128)
    vectors = await provider.embed(["some text"])
    assert len(vectors[0]) == 128
    assert provider.dimensions == 128


async def test_vectors_are_unit_normalized():
    # Cosine similarity assumes normalized vectors; unnormalized ones would
    # let long documents dominate purely by magnitude.
    provider = HashEmbeddingProvider()
    vectors = await provider.embed(["Kubernetes Terraform AWS infrastructure"])
    magnitude = math.sqrt(sum(v * v for v in vectors[0]))
    assert abs(magnitude - 1.0) < 1e-9


async def test_batch_returns_one_vector_per_input_in_order():
    provider = HashEmbeddingProvider()
    texts = ["alpha", "beta", "gamma"]
    vectors = await provider.embed(texts)
    assert len(vectors) == 3
    individually = [(await provider.embed([t]))[0] for t in texts]
    assert vectors == individually


async def test_empty_batch_returns_empty_list():
    assert await HashEmbeddingProvider().embed([]) == []


async def test_empty_text_produces_a_valid_vector():
    # A zero vector would make cosine similarity undefined downstream.
    provider = HashEmbeddingProvider()
    vectors = await provider.embed([""])
    magnitude = math.sqrt(sum(v * v for v in vectors[0]))
    assert abs(magnitude - 1.0) < 1e-9


async def test_similar_text_scores_higher_than_unrelated_text():
    provider = HashEmbeddingProvider()
    base, similar, unrelated = await provider.embed(
        [
            "Python Django PostgreSQL backend development",
            "Python Django PostgreSQL backend engineering",
            "graphic design illustration typography branding",
        ]
    )
    assert cosine_similarity(base, similar) > cosine_similarity(base, unrelated)


async def test_identical_text_scores_essentially_one():
    provider = HashEmbeddingProvider()
    a, b = await provider.embed(["Kubernetes engineer", "Kubernetes engineer"])
    assert cosine_similarity(a, b) > 0.999


async def test_model_name_flags_it_as_non_semantic():
    # Nobody should later mistake these for real semantic embeddings.
    name = HashEmbeddingProvider().model_name
    assert "non-semantic" in name or "hash" in name
