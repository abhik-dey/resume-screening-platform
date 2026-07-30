"""
Cross-dialect UUID type.

Production runs on PostgreSQL, which has a native UUID type. But our API
test suite (Phase 3 onward) runs against an in-memory SQLite database for
speed and isolation, and SQLite has no native UUID type. This TypeDecorator
lets the exact same ORM model work correctly against both — Postgres gets
its efficient native UUID column, SQLite gets a stringified CHAR(36).

This is the standard SQLAlchemy pattern for portable UUID columns.
"""
import uuid

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(str(value)))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(str(value))
        return value
