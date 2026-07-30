"""
Abstract repository interface for User persistence.

This is a "port" in hexagonal-architecture terms: the service layer depends
on this interface, never on a concrete database implementation. That's what
lets AuthService be unit-tested with an in-memory fake and lets us swap
SQLAlchemy for something else later without touching business logic.
"""
from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.user import User


class UserRepository(ABC):
    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        """Return the user with this email, or None if no such user exists."""

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None:
        """Return the user with this id, or None if no such user exists."""

    @abstractmethod
    async def count(self) -> int:
        """Total number of registered users (used for the admin-bootstrap rule)."""

    @abstractmethod
    async def create(self, user: User) -> User:
        """Persist a new user and return the stored representation."""
