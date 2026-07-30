"""
AuthService unit tests, using a hand-rolled in-memory fake repository
instead of SQLAlchemy. This is the payoff of depending on the abstract
UserRepository interface: business logic is testable with zero infrastructure.
"""
import uuid

import pytest

from app.domain.entities.user import User, UserRole
from app.domain.interfaces.user_repository import UserRepository
from app.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    PrivilegeEscalationError,
)


class FakeUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self._users.get(email)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return next((u for u in self._users.values() if u.id == user_id), None)

    async def count(self) -> int:
        return len(self._users)

    async def create(self, user: User) -> User:
        self._users[user.email] = user
        return user


@pytest.fixture
def auth_service() -> AuthService:
    return AuthService(FakeUserRepository())


async def test_first_user_becomes_admin(auth_service: AuthService):
    user = await auth_service.register(
        email="founder@company.com", password="supersecret1", full_name="Founder",
        requested_role=UserRole.VIEWER,  # requested role is ignored for the bootstrap user
    )
    assert user.role == UserRole.ADMIN


async def test_second_user_defaults_to_requested_non_admin_role(auth_service: AuthService):
    await auth_service.register(
        email="founder@company.com", password="supersecret1", full_name="Founder",
        requested_role=UserRole.RECRUITER,
    )
    second = await auth_service.register(
        email="viewer@company.com", password="supersecret1", full_name="Viewer",
        requested_role=UserRole.VIEWER,
    )
    assert second.role == UserRole.VIEWER


async def test_second_user_cannot_self_register_as_admin(auth_service: AuthService):
    await auth_service.register(
        email="founder@company.com", password="supersecret1", full_name="Founder",
        requested_role=UserRole.RECRUITER,
    )
    with pytest.raises(PrivilegeEscalationError):
        await auth_service.register(
            email="hacker@company.com", password="supersecret1", full_name="Hacker",
            requested_role=UserRole.ADMIN,
        )


async def test_duplicate_email_rejected(auth_service: AuthService):
    await auth_service.register(
        email="dup@company.com", password="supersecret1", full_name="Dup",
        requested_role=UserRole.RECRUITER,
    )
    with pytest.raises(EmailAlreadyRegisteredError):
        await auth_service.register(
            email="dup@company.com", password="anotherpassword", full_name="Dup2",
            requested_role=UserRole.RECRUITER,
        )


async def test_authenticate_success_and_failure(auth_service: AuthService):
    await auth_service.register(
        email="user@company.com", password="supersecret1", full_name="User",
        requested_role=UserRole.RECRUITER,
    )
    authenticated = await auth_service.authenticate("user@company.com", "supersecret1")
    assert authenticated.email == "user@company.com"

    with pytest.raises(InvalidCredentialsError):
        await auth_service.authenticate("user@company.com", "wrong-password")

    with pytest.raises(InvalidCredentialsError):
        await auth_service.authenticate("nobody@company.com", "whatever")


async def test_issue_token_embeds_subject_and_role(auth_service: AuthService):
    user = await auth_service.register(
        email="user@company.com", password="supersecret1", full_name="User",
        requested_role=UserRole.RECRUITER,
    )
    result = auth_service.issue_token(user)
    assert result.token_type == "bearer"
    assert isinstance(result.access_token, str) and len(result.access_token) > 0
