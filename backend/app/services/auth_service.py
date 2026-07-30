"""
Auth use-case orchestration: registration, login, token issuance.

Depends only on the abstract UserRepository interface — never on
SQLAlchemy — so this entire class can be unit-tested with an in-memory
fake repository, no database required.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.security import create_access_token, hash_password, verify_password
from app.domain.entities.user import User, UserRole
from app.domain.interfaces.user_repository import UserRepository


class EmailAlreadyRegisteredError(Exception):
    """Raised when registering an email that's already in use."""


class InvalidCredentialsError(Exception):
    """Raised on failed login — deliberately generic to avoid leaking which
    part (email vs. password) was wrong, a standard anti-enumeration practice."""


class PrivilegeEscalationError(Exception):
    """Raised when a public registration attempts to self-assign the admin role."""


@dataclass
class TokenResult:
    access_token: str
    token_type: str = "bearer"


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self._users = user_repository

    async def register(
        self, email: str, password: str, full_name: str, requested_role: UserRole
    ) -> User:
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(f"{email} is already registered")

        user_count = await self._users.count()
        if user_count == 0:
            # Bootstrap: the very first account in the system becomes admin,
            # since there's no existing admin who could grant that role.
            role = UserRole.ADMIN
        elif requested_role == UserRole.ADMIN:
            raise PrivilegeEscalationError(
                "Admin accounts cannot be self-registered; ask an existing admin to promote you"
            )
        else:
            role = requested_role

        user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        return await self._users.create(user)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Incorrect email or password")
        if not user.is_active:
            raise InvalidCredentialsError("Account is disabled")
        return user

    def issue_token(self, user: User) -> TokenResult:
        token = create_access_token(subject=str(user.id), role=user.role.value)
        return TokenResult(access_token=token)
