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

from app.core.config import get_settings
from app.core.security import TokenError, decode_access_token
from app.domain.entities.user import User, UserRole
from app.domain.interfaces.file_storage import FileStorage
from app.infrastructure.db.session import get_db
from app.infrastructure.repositories.sqlalchemy_job_repository import SQLAlchemyJobRepository
from app.infrastructure.repositories.sqlalchemy_resume_repository import SQLAlchemyResumeRepository
from app.infrastructure.repositories.sqlalchemy_user_repository import SQLAlchemyUserRepository
from app.infrastructure.storage.local_file_storage import LocalFileStorage
from app.services.auth_service import AuthService
from app.services.job_service import JobService
from app.services.resume_service import ResumeService

settings = get_settings()

# tokenUrl points Swagger UI's "Authorize" button at our login route.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# A single shared FileStorage instance — local disk today, swappable for an
# S3 adapter later without changing any service or route code.
_file_storage = LocalFileStorage(base_dir=settings.resume_storage_dir)


async def get_user_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyUserRepository:
    return SQLAlchemyUserRepository(db)


async def get_auth_service(
    repo: SQLAlchemyUserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(repo)


async def get_job_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyJobRepository:
    return SQLAlchemyJobRepository(db)


async def get_job_service(
    repo: SQLAlchemyJobRepository = Depends(get_job_repository),
) -> JobService:
    return JobService(repo)


async def get_resume_repository(db: AsyncSession = Depends(get_db)) -> SQLAlchemyResumeRepository:
    return SQLAlchemyResumeRepository(db)


def get_file_storage() -> FileStorage:
    return _file_storage


async def get_resume_service(
    resume_repo: SQLAlchemyResumeRepository = Depends(get_resume_repository),
    job_repo: SQLAlchemyJobRepository = Depends(get_job_repository),
    storage: FileStorage = Depends(get_file_storage),
) -> ResumeService:
    return ResumeService(
        resume_repository=resume_repo,
        job_repository=job_repo,
        file_storage=storage,
        max_upload_size_bytes=settings.max_resume_upload_size_bytes,
    )


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
