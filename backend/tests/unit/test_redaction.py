"""
PII redaction tests.

Logs from a hiring system carry candidate data, and structured logs get
retained and indexed — so a redaction gap is a sustained privacy problem,
not a momentary one.
"""
from app.core.observability.redaction import (
    MAX_TEXT_LENGTH,
    REDACTED,
    redact_dict,
    redact_text,
    redact_value,
)


def test_emails_are_masked():
    assert "jane.doe@example.com" not in redact_text("Contact jane.doe@example.com today")
    assert "[EMAIL]" in redact_text("Contact jane.doe@example.com today")


def test_multiple_emails_are_all_masked():
    result = redact_text("a@b.com and c@d.org")
    assert "@b.com" not in result and "@d.org" not in result


def test_phone_numbers_are_masked():
    for phone in ["555-123-4567", "(555) 123-4567", "+1 555 123 4567", "5551234567"]:
        assert "[PHONE]" in redact_text(f"Call {phone}"), f"missed: {phone}"


def test_long_text_is_truncated():
    long_text = "x" * (MAX_TEXT_LENGTH + 500)
    result = redact_text(long_text)
    assert len(result) < len(long_text)
    assert "truncated" in result


def test_short_text_passes_through():
    assert redact_text("Backend Engineer") == "Backend Engineer"


def test_credential_keys_are_fully_redacted():
    for key in ["password", "api_key", "authorization", "openai_api_key", "github_token"]:
        assert redact_value(key, "supersecret") == REDACTED


def test_pii_keys_are_fully_redacted():
    assert redact_value("email", "jane@example.com") == REDACTED
    assert redact_value("full_name", "Jane Doe") == REDACTED
    assert redact_value("raw_text", "entire resume body") == REDACTED


def test_key_matching_is_case_insensitive():
    assert redact_value("PASSWORD", "x") == REDACTED
    assert redact_value("Email", "x") == REDACTED


def test_nested_dicts_are_redacted():
    data = {"user": {"email": "jane@example.com", "role": "admin"}}
    result = redact_dict(data)
    assert result["user"]["email"] == REDACTED
    assert result["user"]["role"] == "admin"  # non-sensitive preserved


def test_lists_are_redacted():
    data = {"contacts": ["a@b.com", "c@d.com"]}
    result = redact_dict(data)
    assert all("@" not in item for item in result["contacts"])


def test_large_lists_are_capped():
    result = redact_dict({"items": list(range(500))})
    assert len(result["items"]) == 50


def test_recursion_is_depth_limited():
    # A cyclic or pathologically nested structure must not hang the logger.
    deep = current = {}
    for _ in range(20):
        current["nested"] = {}
        current = current["nested"]
    result = redact_dict(deep)
    assert result is not None  # completed without recursion error


def test_non_string_values_pass_through():
    result = redact_dict({"count": 42, "ratio": 0.85, "flag": True, "nothing": None})
    assert result == {"count": 42, "ratio": 0.85, "flag": True, "nothing": None}


def test_useful_operational_fields_survive_redaction():
    # Redaction must not gut the logs of their diagnostic value.
    data = {
        "agent": "resume_parser",
        "duration_ms": 1234,
        "status_code": 200,
        "resume_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    }
    assert redact_dict(data) == data
