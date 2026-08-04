"""Vector store factory — the only place that knows concrete stores exist."""
from app.core.config import Settings
from app.domain.interfaces.vector_store import VectorStore
from app.infrastructure.vector_store.in_memory_vector_store import InMemoryVectorStore
from app.infrastructure.vector_store.qdrant_vector_store import QdrantVectorStore


class VectorStoreConfigurationError(Exception):
    """Raised when the configured vector store backend is unknown."""


def get_vector_store(settings: Settings) -> VectorStore:
    backend = settings.vector_store_backend.lower()
    if backend == "qdrant":
        return QdrantVectorStore(url=settings.qdrant_url)
    if backend == "memory":
        return InMemoryVectorStore()
    raise VectorStoreConfigurationError(
        f"Unknown VECTOR_STORE_BACKEND '{settings.vector_store_backend}'. "
        "Must be 'qdrant' or 'memory'."
    )
