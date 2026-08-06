"""
Retry with backoff for transient LLM provider failures.

WHY THIS EXISTS
---------------
Every LLM provider rate-limits. Hitting a 429 mid-pipeline currently fails
the agent, which halts the run — so a screening job of 20 resumes can die
on resume 17 because the provider wanted a 30-second pause.

The provider usually tells you exactly how long to wait. Honouring that is
the difference between a job that completes slowly and one that fails.

WHAT IS AND ISN'T RETRIED
-------------------------
RETRIED: rate limits (429) and transient server errors (5xx, timeouts,
connection resets). These are expected to succeed on a second attempt.

NOT RETRIED: authentication failures, invalid model names, malformed
requests. Retrying a wrong API key just wastes time and produces the same
error more slowly. This distinction matters — a retry wrapper that
retries everything turns a clear "your model name is wrong" into a
confusing 90-second hang.

Malformed *output* is also not handled here: that's a separate concern,
already retried by call_llm_for_json, which reprompts rather than repeats
the same request.
"""
import asyncio
import random
import re

from app.core.observability.logging_config import get_logger
from app.core.observability.metrics import record_llm_retry

logger = get_logger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 2.0
# Beyond this, waiting is worse than failing: an HTTP request is still open
# and a caller is waiting for an answer.
MAX_DELAY_SECONDS = 60.0


class RetryableProviderError(Exception):
    """A provider failure worth retrying."""


class NonRetryableProviderError(Exception):
    """A provider failure that will fail identically on retry — bad
    credentials, unknown model, malformed request."""


def classify_provider_error(exc: Exception) -> tuple[bool, str]:
    """Decide whether an exception is worth retrying.

    Classifies on the exception's type name and message rather than on
    provider-specific exception classes, so this works across the OpenAI
    and Anthropic SDKs without importing either — keeping the domain free
    of vendor types.
    """
    name = type(exc).__name__
    text = str(exc).lower()

    # Definitely not worth retrying: the same request will fail the same way.
    if any(marker in name for marker in ("Authentication", "PermissionDenied", "NotFound")):
        return False, f"{name} (will not succeed on retry)"
    if any(marker in text for marker in
           ("invalid api key", "incorrect api key", "is not found for api version",
            "no longer available", "unauthorized")):
        return False, "credential or model configuration error"

    # Worth retrying.
    if "RateLimit" in name or "429" in text or "quota" in text or "rate limit" in text:
        return True, "rate limited"
    if any(marker in name for marker in ("Timeout", "Connection", "APIError", "InternalServer")):
        return True, "transient connection or server error"
    if any(code in text for code in ("500", "502", "503", "504", "overloaded")):
        return True, "provider server error"

    # Unknown failures are NOT retried. Retrying something we don't
    # understand risks amplifying load during an incident, and the error
    # surfaces faster this way.
    return False, f"unclassified error ({name})"


def extract_retry_after(exc: Exception) -> float | None:
    """Pull a provider-suggested wait out of the error message.

    Providers frequently say precisely how long to wait ("Please retry in
    48.4s"). Honouring that beats guessing — back off too little and you
    are rate limited again, too much and the job takes needlessly longer.
    """
    text = str(exc)
    for pattern in (
        # "Please retry in 48.400862078s" — OpenAI-compatible endpoints
        r"retry\s+in\s+([\d.]+)\s*s",
        # "'retryDelay': '48s'" — Google's RetryInfo detail, which is the
        # form actually returned by the Gemini endpoint. Missing this meant
        # falling back to a guessed backoff when the provider had told us
        # exactly how long to wait.
        r"retry[_-]?delay[\"']?\s*[:=]\s*[\"']?([\d.]+)",
        r"retry[_-]?after[\"']?\s*[:=]\s*[\"']?([\d.]+)",
        r"try again in\s+([\d.]+)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return min(float(match.group(1)), MAX_DELAY_SECONDS)
            except ValueError:
                continue
    return None


def compute_delay(attempt: int, base: float = DEFAULT_BASE_DELAY) -> float:
    """Exponential backoff with jitter.

    Jitter matters more than it looks: without it, several workers rate
    limited at the same moment all retry at the same moment, reproducing
    the burst that caused the limit.
    """
    delay = min(base * (2 ** attempt), MAX_DELAY_SECONDS)
    return delay * (0.5 + random.random() * 0.5)


async def call_with_retry(
    operation,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    description: str = "LLM call",
):
    """Run `operation` (a zero-arg coroutine function), retrying transient
    failures with backoff.

    Raises NonRetryableProviderError immediately for errors that won't
    improve, and re-raises the last exception once attempts are exhausted.
    """
    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return await operation()
        except Exception as exc:  # noqa: BLE001 -- classified immediately below
            last_exc = exc
            retryable, reason = classify_provider_error(exc)

            if not retryable:
                logger.warning(
                    "provider error will not be retried",
                    extra={"operation": description, "reason": reason,
                           "error_type": type(exc).__name__},
                )
                raise NonRetryableProviderError(f"{reason}: {exc}") from exc

            if attempt == max_attempts - 1:
                logger.error(
                    "provider retries exhausted",
                    extra={"operation": description, "attempts": max_attempts, "reason": reason},
                )
                break

            delay = extract_retry_after(exc) or compute_delay(attempt, base_delay)
            record_llm_retry(reason.replace(" ", "_"))
            logger.warning(
                "retrying after provider error",
                extra={"operation": description, "reason": reason,
                       "attempt": attempt + 1, "delay_seconds": round(delay, 1)},
            )
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]
