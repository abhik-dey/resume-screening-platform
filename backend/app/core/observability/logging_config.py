"""
Structured JSON logging with automatic request correlation and redaction.

JSON rather than text because logs from this system are meant to be
searched and aggregated, and parsing free-form text at query time is a
losing game.

Every record automatically carries the current request_id (from
contextvars) and is passed through PII redaction before serialization.
Redaction happens in the formatter rather than at call sites: relying on
every future logging call to remember is a policy that fails quietly.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.observability.context import get_request_id, get_user_id
from app.core.observability.redaction import redact_dict, redact_text

# Attributes LogRecord always carries; anything else was added by the
# caller as structured context and should appear in the output.
_STANDARD_ATTRS = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message", "asctime",
    }
)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }

        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        user_id = get_user_id()
        if user_id:
            payload["user_id"] = user_id

        extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}
        if extras:
            payload.update(redact_dict(extras))

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # default=str so UUIDs, datetimes, and enums serialize rather than
        # raising inside the logger — a logging failure that masks the
        # original error is a genuinely bad outcome.
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Install the log configuration. Idempotent."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        # Plain text for local development, where JSON is harder to read.
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )
    root.addHandler(handler)

    # uvicorn installs its own handlers; clearing them prevents every
    # request being logged twice in different formats.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
