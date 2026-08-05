"""Tests for logging, context propagation, and metrics."""
import json
import logging

from app.core.observability.context import (
    get_request_id,
    get_user_id,
    new_request_id,
    set_request_id,
    set_user_id,
)
from app.core.observability.logging_config import JSONFormatter, configure_logging
from app.core.observability.metrics import (
    REGISTRY,
    record_agent_run,
    record_llm_call,
    record_llm_retry,
    record_pipeline_run,
    render_metrics,
)


def _format(record_kwargs: dict, message: str = "test message") -> dict:
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="x.py", lineno=1,
        msg=message, args=(), exc_info=None,
    )
    for key, value in record_kwargs.items():
        setattr(record, key, value)
    return json.loads(JSONFormatter().format(record))


def test_log_output_is_valid_json():
    output = _format({})
    assert output["level"] == "INFO"
    assert output["message"] == "test message"
    assert "timestamp" in output


def test_request_id_is_attached_automatically():
    # The point of contextvars: no call site has to remember to pass it.
    set_request_id("abc123")
    try:
        assert _format({})["request_id"] == "abc123"
    finally:
        set_request_id(None)


def test_no_request_id_when_unset():
    set_request_id(None)
    assert "request_id" not in _format({})


def test_structured_extras_appear_in_output():
    output = _format({"agent": "resume_parser", "duration_ms": 123.4})
    assert output["agent"] == "resume_parser"
    assert output["duration_ms"] == 123.4


def test_pii_in_extras_is_redacted():
    output = _format({"email": "jane@example.com", "agent": "parser"})
    assert output["email"] == "[REDACTED]"
    assert output["agent"] == "parser"  # non-PII survives


def test_pii_in_the_message_itself_is_redacted():
    # Log messages are as likely to leak as structured fields.
    output = _format({}, message="Processing resume for jane.doe@example.com")
    assert "jane.doe@example.com" not in output["message"]
    assert "[EMAIL]" in output["message"]


def test_unserializable_values_do_not_break_logging():
    # A logging failure that masks the original error is a bad outcome.
    import uuid
    from datetime import datetime

    output = _format({"id": uuid.uuid4(), "when": datetime.now()})
    assert isinstance(output["id"], str)


def test_exceptions_are_included():
    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="x.py", lineno=1,
        msg="failed", args=(), exc_info=None,
    )
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    output = json.loads(JSONFormatter().format(record))
    assert "ValueError" in output["exception"]


def test_request_ids_are_unique():
    assert len({new_request_id() for _ in range(100)}) == 100


def test_user_id_context_propagates():
    set_user_id("user-42")
    try:
        assert get_user_id() == "user-42"
        assert _format({})["user_id"] == "user-42"
    finally:
        set_user_id(None)


def test_configure_logging_is_idempotent():
    configure_logging(level="INFO")
    configure_logging(level="INFO")
    # Duplicate handlers would double every log line.
    assert len(logging.getLogger().handlers) == 1


def test_context_isolation_between_requests():
    set_request_id("first")
    assert get_request_id() == "first"
    set_request_id("second")
    assert get_request_id() == "second"


# --- Metrics ---

def test_agent_metrics_are_recorded():
    record_agent_run("test_agent_unique_1", success=True, duration_seconds=1.5)
    output = render_metrics().decode()
    assert 'agent_runs_total{agent="test_agent_unique_1",outcome="success"}' in output
    assert "agent_duration_seconds" in output


def test_agent_failures_are_labelled_separately():
    record_agent_run("test_agent_unique_2", success=False, duration_seconds=0.5)
    output = render_metrics().decode()
    assert 'outcome="failure"' in output


def test_llm_call_outcomes_are_distinguished():
    record_llm_call("TestProvider", "success", 2.0)
    record_llm_call("TestProvider", "malformed", 1.0)
    output = render_metrics().decode()
    assert 'llm_calls_total{outcome="success",provider="TestProvider"}' in output
    assert 'llm_calls_total{outcome="malformed",provider="TestProvider"}' in output


def test_llm_retries_are_tracked_by_reason():
    # A rising retry rate is the earliest signal of provider degradation.
    record_llm_retry("malformed_json")
    output = render_metrics().decode()
    assert 'llm_retries_total{reason="malformed_json"}' in output


def test_pipeline_halts_record_the_failing_step():
    record_pipeline_run(halted=True, duration_seconds=5.0, halt_step="parse")
    output = render_metrics().decode()
    assert 'pipeline_halts_total{step="parse"}' in output
    assert 'pipeline_runs_total{outcome="halted"}' in output


def test_metrics_render_in_prometheus_format():
    output = render_metrics().decode()
    assert "# HELP" in output
    assert "# TYPE" in output


def test_dedicated_registry_is_used():
    # Not the global default: process-wide mutable state makes tests
    # order-dependent and re-registration errors common.
    from prometheus_client import REGISTRY as GLOBAL_REGISTRY

    assert REGISTRY is not GLOBAL_REGISTRY


def test_llm_histogram_buckets_suit_llm_latency():
    # Web-default buckets (milliseconds) would put every LLM call in the
    # overflow bucket and make the histogram useless.
    output = render_metrics().decode()
    assert 'llm_duration_seconds_bucket{le="30.0"' in output
