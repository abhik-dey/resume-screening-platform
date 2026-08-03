"""
Shared helper for agents that ask an LLM for structured JSON output.

Extracted after the second agent (Skill Extraction, Phase 7) needed
exactly the same "call LLM, parse JSON, retry once on malformed output"
shape as the first (Resume Parsing, Phase 6). Two genuine occurrences of
the same pattern is the signal to extract, not speculation about a
pattern that might repeat.
"""
import json
from collections.abc import Callable
from typing import TypeVar

from pydantic import ValidationError

from app.domain.interfaces.llm_provider import LLMProvider

T = TypeVar("T")


def strip_markdown_fences(text: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ``` even when told not to."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence (possibly with a language tag)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


async def call_llm_for_json(
    llm: LLMProvider,
    system_prompt: str,
    user_prompt: str,
    validate: Callable[[dict], T],
    build_retry_prompt: Callable[[str], str],
    max_attempts: int = 2,
) -> T | None:
    """Call the LLM, parse its response as JSON, and validate it with
    `validate` (typically a Pydantic model's `model_validate`). Retries up
    to `max_attempts` times total, feeding the previous bad response back
    via `build_retry_prompt` on subsequent attempts. Returns None if every
    attempt fails — callers decide what "no valid output" means for them."""
    last_response = ""
    for attempt in range(max_attempts):
        prompt = user_prompt if attempt == 0 else build_retry_prompt(last_response)
        raw_response = await llm.complete(system_prompt, prompt)
        last_response = raw_response
        try:
            cleaned = strip_markdown_fences(raw_response)
            data = json.loads(cleaned)
            return validate(data)
        except (json.JSONDecodeError, ValidationError, ValueError):
            continue
    return None
