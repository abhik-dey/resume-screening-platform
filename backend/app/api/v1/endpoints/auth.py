"""Auth endpoints: register, login, current-user, and an RBAC demo route."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import get_auth_service, get_current_user, require_roles
from app.api.v1.schemas.auth import TokenResponse, UserCreateRequest, UserResponse
from app.domain.entities.user import User, UserRole
from app.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    PrivilegeEscalationError,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreateRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    try:
        return await auth_service.register(
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            requested_role=payload.role,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PrivilegeEscalationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse)
async def login(
    # OAuth2PasswordRequestForm expects form-encoded `username` + `password`
    # fields (not JSON) — this is what makes Swagger UI's "Authorize" button
    # work out of the box. `username` here is the user's email.
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    try:
        user = await auth_service.authenticate(form_data.username, form_data.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    result = auth_service.issue_token(user)
    return TokenResponse(access_token=result.access_token, token_type=result.token_type)


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/admin-only", response_model=UserResponse)
async def admin_only_example(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
) -> User:
    """Demonstrates an RBAC-protected route — only the ADMIN role may access this."""
    return current_user
