"""
User domain entity.

This module is intentionally framework-agnostic: no FastAPI, no SQLAlchemy,
no Pydantic. It represents what a "user" *means* to the business, not how
it's stored or transported. Infrastructure code converts to/from this shape.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class UserRole(str, Enum):
    """The three roles supported by RBAC in this system.

    Inherits from str so it serializes cleanly through Pydantic and JWTs
    without extra conversion code.
    """

    ADMIN = "admin"
    RECRUITER = "recruiter"
    VIEWER = "viewer"


@dataclass
class User:
    """A registered account. `hashed_password` is never the plaintext password."""

    id: UUID
    email: str
    hashed_password: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
