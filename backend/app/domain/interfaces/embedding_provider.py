"""
Abstract embedding provider interface.

Same adapter pattern as LLMProvider (Phase 6): business logic depends on
this abstraction, never on a specific embedding API. Swapping providers —
or falling back to a local deterministic implementation when no API key is
configured — means selecting a different adapter, not changing any caller.
"""
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector length this provider produces. The vector store needs it
        up front to create a correctly-sized collection, and mismatched
        dimensions are a silent corruption risk if a provider changes."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier recorded alongside stored vectors, so it's possible to
        tell later which model produced them — vectors from different models
        are not comparable."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returning one vector per input in order.

        Batch rather than single-text: embedding APIs charge and rate-limit
        per request, so embedding 20 resumes in one call rather than 20 is a
        material difference."""
