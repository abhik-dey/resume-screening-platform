"""
Cross-dialect UUID and JSON types.

Production runs on PostgreSQL, which has native UUID and JSONB types. But
our test suite (Phase 3 onward) runs against an in-memory SQLite database
for speed and isolation, and SQLite has neither. These type decorators let
the exact same ORM models work correctly against both.
"""
import uuid

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
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


# A single reusable TypeEngine instance: JSONB on Postgres (indexable,
# efficient), plain JSON everywhere else (e.g. SQLite in tests). Import and
# reuse this constant across model columns rather than constructing a new
# variant type per column.
PORTABLE_JSON = JSON().with_variant(JSONB(), "postgresql")
