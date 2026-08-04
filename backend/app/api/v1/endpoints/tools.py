"""Tool listing and invocation endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_tool_registry
from app.api.v1.schemas.tools import (
    ToolDescription,
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolListResponse,
)
from app.domain.entities.user import User
from app.domain.tools.registry import (
    ToolNotFoundError,
    ToolPermissionError,
    ToolRegistry,
    ToolValidationError,
)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


@router.get("", response_model=ToolListResponse)
async def list_tools(
    current_user: User = Depends(get_current_user),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> ToolListResponse:
    """List tools available to the current user, with their input schemas.

    Filtered by role: tools the caller couldn't invoke aren't shown.
    """
    described = registry.list_for_role(current_user.role)
    return ToolListResponse(
        tools=[ToolDescription(**d) for d in described], total=len(described)
    )


@router.post("/{tool_name}/invoke", response_model=ToolInvokeResponse)
async def invoke_tool(
    tool_name: str,
    payload: ToolInvokeRequest | None = None,
    current_user: User = Depends(get_current_user),
    registry: ToolRegistry = Depends(get_tool_registry),
) -> ToolInvokeResponse:
    """Invoke a tool by name.

    Params are validated against the tool's schema and the caller's role is
    checked against the tool's requirement before execution. A tool that
    fails at runtime returns success=false rather than an HTTP error — the
    request was well-formed, the tool just couldn't complete.
    """
    params = payload.params if payload else {}

    try:
        result = await registry.invoke(tool_name, params, current_user.role)
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ToolPermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ToolValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return ToolInvokeResponse(
        tool=tool_name,
        success=result.success,
        data=result.data,
        error=result.error,
        notice=result.notice,
    )
