"""
Request-scoped context.

Uses contextvars so a request ID propagates automatically into every log
line, metric label, and span — without threading a parameter through twenty
function signatures, which nobody maintains consistently.

contextvars (not thread-locals) because this is an async application: a
thread-local would be shared across concurrent coroutines on the same
thread and correlate the wrong requests together.
"""
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def set_user_id(value: str | None) -> None:
    _user_id.set(value)


def get_user_id() -> str | None:
    """The authenticated user's ID — never their email or name, which are PII."""
    return _user_id.get()
