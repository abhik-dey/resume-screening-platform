"""
OpenAI-compatible embedding provider.

Also serves Gemini's free tier via `base_url`, exactly as OpenAIProvider
does for chat completions (Phase 6) — one adapter, two providers, because
Gemini exposes an OpenAI-compatible embeddings endpoint.
"""
from openai import AsyncOpenAI

from app.domain.interfaces.embedding_provider import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self, api_key: str, model: str, dimensions: int, base_url: str | None = None
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(model=self._model, input=texts)
        # Sort by index: the API documents ordered responses, but relying on
        # arrival order would silently mismatch vectors to texts if that ever
        # changed — and a mismatched embedding is invisible until search
        # results are subtly wrong.
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]
