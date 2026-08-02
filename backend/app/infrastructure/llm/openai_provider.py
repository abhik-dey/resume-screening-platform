"""
OpenAI implementation of LLMProvider.

Also doubles as the adapter for any OpenAI-compatible endpoint via
`base_url` — this is how Google's Gemini API is used for free (see
LLM_PROVIDER=openai + OPENAI_BASE_URL in .env.example), without writing
a separate GeminiProvider class.
"""
from openai import AsyncOpenAI

from app.domain.interfaces.llm_provider import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""
