"""
Dependency-injection wiring for the API layer.

This module is the only place that knows how to assemble concrete
implementations (SQLAlchemyUserRepository, AuthService) from the abstract
interfaces the rest of the codebase depends on. Swapping an implementation
later means editing this file, not the routes or services.
"""
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, decode_access_token
from app.domain.entities.user import User, UserRole
from app.infrastructure.db.session import get_db
from app.infrastructure.repositories.sqlalchemy_user_repository import SQLAlchemyUserRepository
from app.services.auth_service import AuthService

# tokenUrl points Swagger UI's "Authorize" button at our login route.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_user_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyUserRepository:
    return SQLAlchemyUserRepository(db)


async def get_auth_service(
    repo: SQLAlchemyUserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(repo)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    repo: SQLAlchemyUserRepository = Depends(get_user_repository),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        raise credentials_error from exc

    raw_user_id = payload.get("sub")
    if raw_user_id is None:
        raise credentials_error

    user = await repo.get_by_id(UUID(raw_user_id))
    if user is None or not user.is_active:
        raise credentials_error
    return user


def require_roles(*allowed_roles: UserRole):
    """Dependency factory enforcing RBAC on a route.

    Usage: `current_user: User = Depends(require_roles(UserRole.ADMIN))`
    """

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return _check
