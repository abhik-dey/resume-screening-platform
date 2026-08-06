"""
Retry logic tests.

The classification tests matter most. Retrying a bad API key wastes time
and produces the same error more slowly; not retrying a rate limit fails a
job that would have succeeded. Getting the boundary right is the whole
value of this module.
"""
import pytest

from app.infrastructure.llm.retry import (
    MAX_DELAY_SECONDS,
    NonRetryableProviderError,
    call_with_retry,
    classify_provider_error,
    compute_delay,
    extract_retry_after,
)


class RateLimitError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class APITimeoutError(Exception):
    pass


# --- Classification: what gets retried ---

def test_rate_limits_are_retried():
    retryable, reason = classify_provider_error(RateLimitError("429 quota exceeded"))
    assert retryable is True
    assert "rate limited" in reason


def test_the_real_gemini_quota_error_is_retried():
    # The exact error hit during development.
    exc = Exception(
        "Error code: 429 - You exceeded your current quota. "
        "Quota exceeded for metric: generate_content_free_tier_requests"
    )
    assert classify_provider_error(exc)[0] is True


def test_timeouts_are_retried():
    assert classify_provider_error(APITimeoutError("request timed out"))[0] is True


def test_server_errors_are_retried():
    for message in ("503 Service Unavailable", "502 Bad Gateway", "model is overloaded"):
        assert classify_provider_error(Exception(message))[0] is True, message


# --- Classification: what must NOT be retried ---

def test_authentication_errors_are_not_retried():
    # Retrying a bad key just produces the same error more slowly.
    retryable, reason = classify_provider_error(AuthenticationError("invalid api key"))
    assert retryable is False
    assert "retry" in reason.lower() or "credential" in reason.lower()


def test_unknown_model_is_not_retried():
    # The exact error from using an OpenAI model name against Gemini.
    exc = NotFoundError(
        "models/text-embedding-3-small is not found for API version v1main"
    )
    assert classify_provider_error(exc)[0] is False


def test_retired_model_is_not_retried():
    exc = Exception("This model models/gemini-2.5-flash is no longer available to new users")
    assert classify_provider_error(exc)[0] is False


def test_unclassified_errors_are_not_retried():
    # Retrying something we don't understand risks amplifying load during
    # an incident, and surfaces the real error more slowly.
    retryable, reason = classify_provider_error(ValueError("something unexpected"))
    assert retryable is False
    assert "unclassified" in reason


# --- Provider-suggested delays ---

def test_provider_suggested_delay_is_honoured():
    # Guessing beats nothing, but the provider knows better.
    assert extract_retry_after(Exception("Please retry in 48.4s")) == pytest.approx(48.4)


def test_various_retry_after_formats_are_parsed():
    assert extract_retry_after(Exception("'retryDelay': '30'")) == pytest.approx(30.0)
    assert extract_retry_after(Exception("try again in 5 seconds")) == pytest.approx(5.0)


def test_suggested_delay_is_capped():
    # A provider suggesting an hour shouldn't hang an open HTTP request.
    assert extract_retry_after(Exception("retry in 9999s")) == MAX_DELAY_SECONDS


def test_absent_delay_returns_none():
    assert extract_retry_after(Exception("no timing information here")) is None


# --- Backoff ---

def test_delay_grows_exponentially():
    assert compute_delay(2) > compute_delay(0)


def test_delay_is_capped():
    assert compute_delay(20) <= MAX_DELAY_SECONDS


def test_delay_is_jittered():
    # Without jitter, workers rate limited together retry together,
    # reproducing the burst that caused the limit.
    assert len({compute_delay(1) for _ in range(20)}) > 1


# --- Retry behavior ---

async def test_successful_call_does_not_retry():
    calls = []

    async def op():
        calls.append(1)
        return "ok"

    assert await call_with_retry(op) == "ok"
    assert len(calls) == 1


async def test_transient_failure_is_retried_then_succeeds():
    calls = []

    async def op():
        calls.append(1)
        if len(calls) < 2:
            raise RateLimitError("429 rate limit")
        return "recovered"

    result = await call_with_retry(op, base_delay=0.01)
    assert result == "recovered"
    assert len(calls) == 2


async def test_non_retryable_failure_raises_immediately():
    calls = []

    async def op():
        calls.append(1)
        raise AuthenticationError("invalid api key")

    with pytest.raises(NonRetryableProviderError):
        await call_with_retry(op, base_delay=0.01)
    assert len(calls) == 1  # no wasted attempts


async def test_retries_are_bounded():
    calls = []

    async def op():
        calls.append(1)
        raise RateLimitError("429")

    with pytest.raises(RateLimitError):
        await call_with_retry(op, max_attempts=3, base_delay=0.01)
    assert len(calls) == 3
