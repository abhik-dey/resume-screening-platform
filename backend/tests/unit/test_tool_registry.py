"""
Tool registry tests — validation, authorization, and error containment.

These matter because the registry is the single choke point where every
tool invocation is checked. A gap here bypasses every tool's protections
at once.
"""
import pytest

from app.domain.entities.user import UserRole
from app.domain.tools.base import Tool, ToolError, ToolResult
from app.domain.tools.registry import (
    ToolNotFoundError,
    ToolPermissionError,
    ToolRegistry,
    ToolValidationError,
    validate_params,
)


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes its input"
    required_role = UserRole.VIEWER

    @property
    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "maxLength": 20},
                "count": {"type": "integer", "minimum": 1, "maximum": 10},
                "mode": {"type": "string", "enum": ["a", "b"]},
            },
            "required": ["message"],
        }

    async def execute(self, params):
        return ToolResult(success=True, data={"echoed": params["message"]})


class _AdminTool(Tool):
    name = "admin_only"
    description = "Requires admin"
    required_role = UserRole.ADMIN

    @property
    def input_schema(self):
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, params):
        return ToolResult(success=True)


class _RecruiterTool(Tool):
    name = "recruiter_tool"
    description = "Requires recruiter"
    required_role = UserRole.RECRUITER

    @property
    def input_schema(self):
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, params):
        return ToolResult(success=True)


class _RaisingTool(Tool):
    name = "raises"
    description = "Raises ToolError"

    @property
    def input_schema(self):
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, params):
        raise ToolError("deliberate tool failure")


class _CrashingTool(Tool):
    name = "crashes"
    description = "Raises an unexpected exception"

    @property
    def input_schema(self):
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, params):
        raise RuntimeError("unexpected bug in tool")


@pytest.fixture
def registry():
    return ToolRegistry([_EchoTool(), _AdminTool(), _RecruiterTool(), _RaisingTool(), _CrashingTool()])


async def test_successful_invocation(registry):
    result = await registry.invoke("echo", {"message": "hello"}, UserRole.VIEWER)
    assert result.success is True
    assert result.data["echoed"] == "hello"


async def test_unknown_tool_raises(registry):
    with pytest.raises(ToolNotFoundError):
        await registry.invoke("nope", {}, UserRole.ADMIN)


async def test_insufficient_role_is_rejected(registry):
    with pytest.raises(ToolPermissionError):
        await registry.invoke("admin_only", {}, UserRole.RECRUITER)


async def test_higher_role_can_invoke_lower_role_tools(registry):
    # Roles are hierarchical: an admin can do anything a viewer can.
    result = await registry.invoke("echo", {"message": "hi"}, UserRole.ADMIN)
    assert result.success is True


async def test_recruiter_cannot_invoke_admin_tool_but_can_invoke_own(registry):
    result = await registry.invoke("recruiter_tool", {}, UserRole.RECRUITER)
    assert result.success is True
    with pytest.raises(ToolPermissionError):
        await registry.invoke("admin_only", {}, UserRole.RECRUITER)


async def test_viewer_cannot_invoke_recruiter_tool(registry):
    with pytest.raises(ToolPermissionError):
        await registry.invoke("recruiter_tool", {}, UserRole.VIEWER)


async def test_missing_required_param_is_rejected(registry):
    with pytest.raises(ToolValidationError, match="Missing required"):
        await registry.invoke("echo", {}, UserRole.VIEWER)


async def test_unknown_param_is_rejected(registry):
    # A typo'd parameter silently doing nothing is a confusing failure.
    with pytest.raises(ToolValidationError, match="Unknown parameter"):
        await registry.invoke("echo", {"message": "hi", "typo": 1}, UserRole.VIEWER)


async def test_tool_error_becomes_a_failed_result_not_an_exception(registry):
    result = await registry.invoke("raises", {}, UserRole.VIEWER)
    assert result.success is False
    assert "deliberate tool failure" in result.error


async def test_unexpected_exception_is_contained(registry):
    # A bug inside a tool must not surface as a 500 from the endpoint.
    result = await registry.invoke("crashes", {}, UserRole.VIEWER)
    assert result.success is False
    assert "RuntimeError" in result.error


def test_list_for_role_hides_tools_the_caller_cannot_use(registry):
    viewer_tools = {t["name"] for t in registry.list_for_role(UserRole.VIEWER)}
    admin_tools = {t["name"] for t in registry.list_for_role(UserRole.ADMIN)}

    assert "admin_only" not in viewer_tools
    assert "recruiter_tool" not in viewer_tools
    assert "echo" in viewer_tools
    assert "admin_only" in admin_tools


def test_duplicate_registration_is_rejected():
    registry = ToolRegistry([_EchoTool()])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_EchoTool())


def test_describe_exposes_the_contract(registry):
    described = registry.get("echo").describe()
    assert described["name"] == "echo"
    assert described["required_role"] == "viewer"
    assert "properties" in described["input_schema"]
    assert described["is_mutating"] is False


def test_type_validation():
    schema = {
        "type": "object",
        "properties": {"s": {"type": "string"}, "i": {"type": "integer"}, "b": {"type": "boolean"}},
        "required": [],
    }
    validate_params({"s": "ok", "i": 1, "b": True}, schema)

    with pytest.raises(ToolValidationError):
        validate_params({"s": 123}, schema)
    with pytest.raises(ToolValidationError):
        validate_params({"i": "not an int"}, schema)
    with pytest.raises(ToolValidationError):
        validate_params({"b": "not a bool"}, schema)


def test_integer_bounds_are_enforced():
    schema = {
        "type": "object",
        "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 10}},
        "required": [],
    }
    validate_params({"n": 5}, schema)
    with pytest.raises(ToolValidationError, match=">= 1"):
        validate_params({"n": 0}, schema)
    with pytest.raises(ToolValidationError, match="<= 10"):
        validate_params({"n": 11}, schema)


def test_string_length_and_enum_are_enforced():
    schema = {
        "type": "object",
        "properties": {
            "s": {"type": "string", "maxLength": 5},
            "m": {"type": "string", "enum": ["a", "b"]},
        },
        "required": [],
    }
    validate_params({"s": "short", "m": "a"}, schema)
    with pytest.raises(ToolValidationError, match="exceeds"):
        validate_params({"s": "way too long"}, schema)
    with pytest.raises(ToolValidationError, match="one of"):
        validate_params({"m": "z"}, schema)


def test_booleans_are_not_accepted_as_integers():
    # bool is a subclass of int in Python, so `isinstance(True, int)` is
    # True — an easy way to let `{"limit": true}` through unnoticed.
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": []}
    with pytest.raises(ToolValidationError):
        validate_params({"n": True}, schema)
