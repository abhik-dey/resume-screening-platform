"""
Password hashing and JWT issuance/verification.

Deliberately isolated from FastAPI and SQLAlchemy so it can be unit-tested
(and reasoned about) in complete isolation from the web layer or a database.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# bcrypt truncates passwords at 72 bytes; that's a passlib/bcrypt limitation,
# not a bug — Pydantic schema validation caps password length well below
# that, so it's a non-issue here, but worth knowing if this ever changes.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage. Never store plaintext passwords."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored hash."""
    return _pwd_context.verify(plain_password, hashed_password)


class TokenError(Exception):
    """Raised when a JWT is missing, malformed, expired, or otherwise invalid."""


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:
    """Issue a signed JWT. `subject` is the user's id (as a string), `role` is embedded
    so downstream RBAC checks don't need a database round-trip on every request."""
    expire_delta = timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    expire_at = datetime.now(timezone.utc) + expire_delta
    payload: dict[str, Any] = {"sub": subject, "role": role, "exp": expire_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT, raising TokenError on any failure."""
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid") from exc
