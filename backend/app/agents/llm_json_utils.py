"""
Shared helper for agents that ask an LLM for structured JSON output.

Extracted after the second agent (Skill Extraction, Phase 7) needed
exactly the same "call LLM, parse JSON, retry once on malformed output"
shape as the first (Resume Parsing, Phase 6). Two genuine occurrences of
the same pattern is the signal to extract, not speculation about a
pattern that might repeat.
"""
import json
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import ValidationError

from app.core.observability.logging_config import get_logger
from app.core.observability.metrics import record_llm_call, record_llm_retry
from app.domain.interfaces.llm_provider import LLMProvider

logger = get_logger(__name__)

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
    # Instrumented here because this is the single path every structured
    # LLM call takes — a rising retry rate is the earliest signal that a
    # provider or prompt is degrading, and it's otherwise invisible.
    provider_name = type(llm).__name__
    last_response = ""

    for attempt in range(max_attempts):
        prompt = user_prompt if attempt == 0 else build_retry_prompt(last_response)
        started = time.perf_counter()
        try:
            raw_response = await llm.complete(system_prompt, prompt)
        except Exception:
            record_llm_call(provider_name, "error", time.perf_counter() - started)
            raise

        duration = time.perf_counter() - started
        last_response = raw_response

        try:
            cleaned = strip_markdown_fences(raw_response)
            data = json.loads(cleaned)
            result = validate(data)
        except json.JSONDecodeError:
            record_llm_call(provider_name, "malformed", duration)
            record_llm_retry("malformed_json")
            logger.warning(
                "LLM returned malformed JSON",
                extra={"provider": provider_name, "attempt": attempt + 1},
            )
            continue
        except (ValidationError, ValueError):
            record_llm_call(provider_name, "malformed", duration)
            record_llm_retry("validation_error")
            logger.warning(
                "LLM output failed schema validation",
                extra={"provider": provider_name, "attempt": attempt + 1},
            )
            continue

        record_llm_call(provider_name, "success", duration)
        return result

    return None
