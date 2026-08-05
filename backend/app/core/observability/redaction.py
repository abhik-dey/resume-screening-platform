"""
PII redaction for logs and traces.

WHY THIS IS PART OF THE OBSERVABILITY PHASE, NOT AN AFTERTHOUGHT
----------------------------------------------------------------
Structured logging makes it dramatically easier to leak personal data at
scale. Unstructured logs get grepped occasionally; structured logs get
shipped to a search index, retained for months, and read by people who
never touched the hiring system.

This platform's logs would otherwise carry candidate names, email
addresses, phone numbers, and resume text. So redaction is a default
behavior of the log formatter, not something each call site must remember.

WHAT IT CATCHES: email addresses, phone numbers, long free-text blobs
(resume content), and values under keys known to hold PII.

WHAT IT DOESN'T: a candidate's name in the middle of a sentence. Names are
not pattern-matchable, which is exactly why free-text values are truncated
rather than trusted. Stated plainly rather than implying the redaction is
complete.
"""
import re
from typing import Any

_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Deliberately loose: catching a false positive in a log is harmless,
# missing a real phone number is not.
_PHONE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")

# Keys whose values are redacted entirely regardless of content.
SENSITIVE_KEYS = frozenset(
    {
        "password", "hashed_password", "token", "access_token", "api_key",
        "authorization", "secret", "jwt_secret_key", "openai_api_key",
        "anthropic_api_key", "github_token",
        # Domain PII
        "email", "phone", "full_name", "candidate_name", "raw_text",
        "resume_text", "content",
    }
)

# Free text longer than this is truncated: resume bodies and LLM prompts
# both land here, and neither belongs in a log line in full.
MAX_TEXT_LENGTH = 200

REDACTED = "[REDACTED]"


def redact_text(value: str) -> str:
    """Mask emails and phone numbers, and truncate long free text."""
    masked = _EMAIL.sub("[EMAIL]", value)
    masked = _PHONE.sub("[PHONE]", masked)
    if len(masked) > MAX_TEXT_LENGTH:
        masked = masked[:MAX_TEXT_LENGTH] + f"...[truncated, {len(value)} chars total]"
    return masked


def redact_value(key: str, value: Any, _depth: int = 0) -> Any:
    """Redact a single key/value pair, recursing into containers.

    Depth-limited: deeply nested structures in a log line are already a
    problem, and unbounded recursion on a cyclic structure would be worse.
    """
    if _depth > 6:
        return "[MAX_DEPTH]"

    if key.lower() in SENSITIVE_KEYS:
        return REDACTED

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(k, v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(key, item, _depth + 1) for item in value][:50]
    return value


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Redact an entire structure. Used by the log formatter on every record."""
    return {k: redact_value(k, v) for k, v in data.items()}
