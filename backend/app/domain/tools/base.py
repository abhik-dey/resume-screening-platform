"""
Tool abstraction with an MCP-compatible shape.

SCOPE NOTE: this is an internal tool registry, not a JSON-RPC MCP server.
The valuable part of MCP for this codebase is the tool *contract* — a
uniform, self-describing, schema-validated, permission-checked interface an
LLM can call. The transport layer (stdio/SSE JSON-RPC) is a separate
deployment artifact that nothing in this platform would currently consume,
so it's deliberately out of scope rather than half-implemented.

Every tool declares:
  - a JSON schema for its input, validated before execution
  - the minimum role required to invoke it
  - whether it mutates state

The role declaration matters: route-level RBAC isn't sufficient when a
single endpoint dispatches to many tools of differing sensitivity. Reading
a candidate's resume and drafting an email to them are not the same
permission.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.domain.entities.user import UserRole


@dataclass
class ToolResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # Human-readable note about constraints applied — e.g. that an email was
    # drafted rather than sent. Surfaced so a caller (or an LLM reading the
    # result) isn't left assuming an action occurred that didn't.
    notice: str | None = None


class ToolError(Exception):
    """Raised when a tool cannot execute. Caught by the registry and turned
    into a failed ToolResult rather than propagating."""


class Tool(ABC):
    """Base class for all tools."""

    name: str
    description: str
    # Minimum role. VIEWER is the least privileged, so a VIEWER-level tool
    # is callable by everyone.
    required_role: UserRole = UserRole.VIEWER
    is_mutating: bool = False
    # Tools that reach outside the system (network, filesystem) are flagged
    # so a caller can see at a glance which have external side effects.
    has_external_effects: bool = False

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema describing this tool's parameters."""

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Run the tool. Params are already schema-validated by the registry."""

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "required_role": self.required_role.value,
            "is_mutating": self.is_mutating,
            "has_external_effects": self.has_external_effects,
        }
