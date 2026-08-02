"""
Abstract LLM provider interface.

Every agent depends on THIS interface, never on the `openai` or `anthropic`
SDKs directly — exactly the dependency-inversion rule from Phase 1. Adding
a new provider (Gemini, Llama, Qwen, ...) means writing one new adapter
class; it never touches agent logic.
"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a system + user prompt to the LLM and return its raw text response.

        Deliberately the simplest possible contract (text in, text out) —
        callers are responsible for instructing the model on output format
        (e.g. "respond with JSON only") and for parsing/validating the result.
        """
