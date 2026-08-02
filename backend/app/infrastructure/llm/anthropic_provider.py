"""Anthropic implementation of LLMProvider."""
from anthropic import AsyncAnthropic

from app.domain.interfaces.llm_provider import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0,
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        return "".join(text_blocks)
