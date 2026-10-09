"""Tool registry and executor tests, including hostile arguments."""

from __future__ import annotations

import pytest

from nova.config.settings import SecuritySettings
from nova.providers.base import ToolCall
from nova.security.policy import Permission, PolicyEngine
from nova.tools.demo import demo_registry
from nova.tools.executor import (
    STATUS_DENIED,
    STATUS_INVALID,
    STATUS_OK,
    STATUS_UNKNOWN,
    ToolExecutor,
    ToolResult,
)
from nova.tools.registry import ToolDefinition, ToolRegistry


def executor(security: SecuritySettings | None = None) -> ToolExecutor:
    return ToolExecutor(demo_registry(), PolicyEngine(security or SecuritySettings()))


async def test_get_time_returns_a_timestamp():
    result = await executor().execute(ToolCall("get_time", {}))
    assert result.status == STATUS_OK
    assert "T" in result.detail


async def test_echo_returns_the_text():
    result = await executor().execute(ToolCall("echo", {"text": "hello"}))
    assert result.status == STATUS_OK
    assert result.detail == "hello"


async def test_unknown_tool_is_reported():
    result = await executor().execute(ToolCall("rm_rf", {}))
    assert result.status == STATUS_UNKNOWN
    assert "no such tool" in result.detail


async def test_system_info_ok():
    result = await executor().execute(ToolCall("get_system_info", {"detail": "platform"}))
    assert result.status == STATUS_OK
    assert "platform=" in result.detail


# -- argument validation ---------------------------------------------------


async def test_missing_required_argument_is_rejected():
    result = await executor().execute(ToolCall("echo", {}))
    assert result.status == STATUS_INVALID
    assert "required" in result.detail


async def test_wrong_argument_type_is_rejected():
    result = await executor().execute(ToolCall("echo", {"text": 42}))
    assert result.status == STATUS_INVALID


async def test_extra_arguments_are_rejected():
    """A model must not be able to smuggle parameters past the schema."""
    result = await executor().execute(
        ToolCall("echo", {"text": "hi", "path": "C:/Windows/System32"})
    )
    assert result.status == STATUS_INVALID
    assert "not allowed" in result.detail


async def test_oversized_argument_is_rejected():
    result = await executor().execute(ToolCall("echo", {"text": "x" * 5000}))
    assert result.status == STATUS_INVALID


async def test_invalid_enum_is_rejected():
    result = await executor().execute(ToolCall("get_system_info", {"detail": "secrets"}))
    assert result.status == STATUS_INVALID


async def test_non_object_arguments_are_rejected():
    result = await executor().execute(ToolCall("echo", "just a string"))  # type: ignore[arg-type]
    assert result.status == STATUS_INVALID


async def test_handler_is_not_called_when_arguments_are_invalid():
    calls: list[dict] = []

    def handler(args: dict) -> str:
        calls.append(args)
        return "ran"

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="strict_tool",
            description="test",
            parameters={
                "type": "object",
                "properties": {"n": {"type": "integer"}},
                "required": ["n"],
                "additionalProperties": False,
            },
            handler=handler,
            permission=None,
        )
    )
    result = await ToolExecutor(registry, PolicyEngine(SecuritySettings())).execute(
        ToolCall("strict_tool", {"n": "not an int"})
    )
    assert result.status == STATUS_INVALID
    assert calls == []


# -- policy gate -----------------------------------------------------------


async def test_policy_denial_blocks_the_handler():
    calls: list[dict] = []

    def handler(args: dict) -> str:
        calls.append(args)
        return "ran"

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="file_reader",
            description="test",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=handler,
            permission=Permission.FS_READ,
        )
    )
    # No allowed folders configured -> the policy engine denies by default.
    result = await ToolExecutor(registry, PolicyEngine(SecuritySettings())).execute(
        ToolCall("file_reader", {})
    )
    assert result.status == STATUS_DENIED
    assert calls == []


async def test_permission_requiring_confirmation_is_blocked_for_now():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="clip_reader",
            description="test",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda _args: "clipboard contents",
            permission=Permission.CLIPBOARD_READ,
        )
    )
    result = await ToolExecutor(registry, PolicyEngine(SecuritySettings())).execute(
        ToolCall("clip_reader", {})
    )
    assert result.status == STATUS_DENIED
    assert "confirmation" in result.detail


# -- registry --------------------------------------------------------------


def test_registry_exposes_provider_specs():
    specs = {spec.name for spec in demo_registry().provider_specs()}
    assert specs == {"get_time", "get_system_info", "echo"}


def test_duplicate_registration_is_rejected():
    registry = demo_registry()
    with pytest.raises(ValueError):
        registry.register(demo_registry().get("echo"))  # type: ignore[arg-type]


def test_args_summary_is_single_line():
    result = ToolResult(name="echo", status=STATUS_OK, detail="x", args={"text": "a" * 500})
    assert "\n" not in result.args_summary
    assert len(result.args_summary) <= 120
