"""
Tool registry — validation, authorization, and dispatch.

Three checks happen here rather than in each tool, so a new tool can't
accidentally skip one:
  1. Does the tool exist?
  2. Is the caller's role sufficient?
  3. Do the params satisfy the tool's schema?

Only then does the tool run, and any exception it raises is captured as a
failed ToolResult rather than surfacing as a 500.
"""
from typing import Any

from app.domain.entities.user import UserRole
from app.domain.tools.base import Tool, ToolError, ToolResult

# Ordered least to most privileged, for comparison.
_ROLE_RANK = {UserRole.VIEWER: 0, UserRole.RECRUITER: 1, UserRole.ADMIN: 2}


class ToolNotFoundError(Exception):
    pass


class ToolPermissionError(Exception):
    pass


class ToolValidationError(Exception):
    pass


def _role_satisfies(actual: UserRole, required: UserRole) -> bool:
    return _ROLE_RANK.get(actual, -1) >= _ROLE_RANK.get(required, 99)


def validate_params(params: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate params against a minimal subset of JSON Schema.

    Deliberately hand-rolled rather than pulling in jsonschema: the schemas
    here are simple (flat objects with typed properties), and the subset
    needed is small enough that an extra dependency isn't justified. If
    schemas grow nested or conditional, swap this for the real library
    rather than extending this function.
    """
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for field_name in required:
        if field_name not in params or params[field_name] is None:
            raise ToolValidationError(f"Missing required parameter: '{field_name}'")

    for key, value in params.items():
        if key not in properties:
            # Rejecting unknown params rather than ignoring them: a typo'd
            # parameter name silently doing nothing is a confusing failure.
            raise ToolValidationError(
                f"Unknown parameter: '{key}'. Allowed: {sorted(properties.keys())}"
            )
        expected = properties[key].get("type")
        if value is None:
            continue
        if expected == "string" and not isinstance(value, str):
            raise ToolValidationError(f"Parameter '{key}' must be a string")
        if expected == "integer" and not isinstance(value, int) or (
            expected == "integer" and isinstance(value, bool)
        ):
            raise ToolValidationError(f"Parameter '{key}' must be an integer")
        if expected == "boolean" and not isinstance(value, bool):
            raise ToolValidationError(f"Parameter '{key}' must be a boolean")
        if expected == "array" and not isinstance(value, list):
            raise ToolValidationError(f"Parameter '{key}' must be an array")

        if expected == "integer":
            minimum, maximum = properties[key].get("minimum"), properties[key].get("maximum")
            if minimum is not None and value < minimum:
                raise ToolValidationError(f"Parameter '{key}' must be >= {minimum}")
            if maximum is not None and value > maximum:
                raise ToolValidationError(f"Parameter '{key}' must be <= {maximum}")

        if expected == "string":
            max_length = properties[key].get("maxLength")
            if max_length is not None and len(value) > max_length:
                raise ToolValidationError(f"Parameter '{key}' exceeds {max_length} characters")
            enum = properties[key].get("enum")
            if enum is not None and value not in enum:
                raise ToolValidationError(f"Parameter '{key}' must be one of {enum}")


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(
                f"Tool '{name}' not found. Available: {sorted(self._tools.keys())}"
            )
        return tool

    def list_for_role(self, role: UserRole) -> list[dict[str, Any]]:
        """Only tools the caller could actually invoke.

        Listing tools someone can't use invites them to try and get a 403 —
        and for an LLM consumer, it invites hallucinated capability.
        """
        return [
            tool.describe()
            for tool in sorted(self._tools.values(), key=lambda t: t.name)
            if _role_satisfies(role, tool.required_role)
        ]

    def list_all(self) -> list[dict[str, Any]]:
        return [tool.describe() for tool in sorted(self._tools.values(), key=lambda t: t.name)]

    async def invoke(self, name: str, params: dict[str, Any], role: UserRole) -> ToolResult:
        tool = self.get(name)

        if not _role_satisfies(role, tool.required_role):
            raise ToolPermissionError(
                f"Tool '{name}' requires role '{tool.required_role.value}' "
                f"(caller has '{role.value}')"
            )

        validate_params(params, tool.input_schema)

        try:
            return await tool.execute(params)
        except ToolError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 -- a tool bug must not 500 the endpoint
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
