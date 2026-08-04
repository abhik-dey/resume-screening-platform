"""
Embedding provider factory.

The only place that knows concrete embedding adapters exist. The "auto"
mode is deliberate: a project that silently fails without an API key is a
project most people never see working, so the default degrades to the
deterministic local provider rather than erroring.
"""
from app.core.config import Settings
from app.domain.interfaces.embedding_provider import EmbeddingProvider
from app.infrastructure.embeddings.hash_embedding_provider import HashEmbeddingProvider
from app.infrastructure.embeddings.openai_embedding_provider import OpenAIEmbeddingProvider


class EmbeddingConfigurationError(Exception):
    """Raised when an explicitly requested provider can't be configured."""


def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    mode = settings.embedding_provider.lower()

    if mode == "local":
        return HashEmbeddingProvider()

    if mode == "openai":
        if not settings.openai_api_key:
            raise EmbeddingConfigurationError(
                "EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY. Use "
                "EMBEDDING_PROVIDER=local for the no-API-key fallback."
            )
        return _build_openai(settings)

    if mode == "auto":
        # Degrade gracefully rather than failing: no key means local.
        if settings.openai_api_key:
            return _build_openai(settings)
        return HashEmbeddingProvider()

    raise EmbeddingConfigurationError(
        f"Unknown EMBEDDING_PROVIDER '{settings.embedding_provider}'. "
        "Must be 'auto', 'openai', or 'local'."
    )


def _build_openai(settings: Settings) -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        base_url=settings.openai_base_url or None,
    )
