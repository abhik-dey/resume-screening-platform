"""Pydantic schemas for tool invocation."""
from typing import Any

from pydantic import BaseModel, Field


class ToolDescription(BaseModel):
    name: str
    description: str
    input_schema: dict
    required_role: str
    is_mutating: bool
    has_external_effects: bool


class ToolListResponse(BaseModel):
    """Only tools the caller can actually invoke.

    Listing unusable tools invites 403s and, for an LLM consumer, invites
    hallucinated capability.
    """

    tools: list[ToolDescription]
    total: int


class ToolInvokeRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ToolInvokeResponse(BaseModel):
    tool: str
    success: bool
    data: dict
    error: str | None = None
    # Constraints applied, e.g. "drafted, not sent" — surfaced so a caller
    # never assumes an action occurred that didn't.
    notice: str | None = None
