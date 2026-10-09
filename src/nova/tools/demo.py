"""Harmless demo tools.

Phase 3 registers only read-only / side-effect-free tools. File, app and shell
tools arrive in Phase 5, behind the approval workflow.
"""

from __future__ import annotations

import os
import platform
import shutil
from datetime import datetime
from typing import Any

from nova.security.policy import Permission
from nova.tools.registry import ToolDefinition, ToolRegistry

_EMPTY_OBJECT: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}


def _get_time(_args: dict[str, Any]) -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _echo(args: dict[str, Any]) -> str:
    return str(args["text"])


def _system_info(args: dict[str, Any]) -> str:
    detail = args.get("detail", "all")
    parts: list[str] = []
    if detail in ("platform", "all"):
        parts.append(f"platform={platform.system()} {platform.release()} ({platform.machine()})")
    if detail in ("cpu", "all"):
        parts.append(f"cpus={os.cpu_count() or 0}")
    if detail in ("memory", "all"):
        try:
            import psutil

            memory = psutil.virtual_memory()
            parts.append(f"ram_total_gb={memory.total / 1024**3:.1f}")
            parts.append(f"ram_used_pct={memory.percent:.0f}")
        except Exception:
            parts.append("ram=unavailable")
    if detail in ("disk", "all"):
        try:
            usage = shutil.disk_usage(".")
            parts.append(f"disk_free_gb={usage.free / 1024**3:.1f}")
            parts.append(f"disk_total_gb={usage.total / 1024**3:.1f}")
        except Exception:
            parts.append("disk=unavailable")
    return ", ".join(parts) if parts else "no detail requested"


GET_TIME = ToolDefinition(
    name="get_time",
    description="Return the current local date and time.",
    parameters=_EMPTY_OBJECT,
    permission=Permission.SYSTEM_INFO,
    handler=_get_time,
)

GET_SYSTEM_INFO = ToolDefinition(
    name="get_system_info",
    description="Report basic information about this computer.",
    parameters={
        "type": "object",
        "properties": {
            "detail": {
                "type": "string",
                "enum": ["cpu", "memory", "disk", "platform", "all"],
                "description": "Which aspect to report.",
            }
        },
        "required": [],
        "additionalProperties": False,
    },
    permission=Permission.SYSTEM_INFO,
    handler=_system_info,
)

ECHO = ToolDefinition(
    name="echo",
    description="Echo the given text back. Useful for testing the tool pipeline.",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "maxLength": 500,
                "description": "The text to echo.",
            }
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    permission=Permission.SYSTEM_INFO,
    handler=_echo,
)


def register_demo_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(GET_TIME)
    registry.register(GET_SYSTEM_INFO)
    registry.register(ECHO)
    return registry


def demo_registry() -> ToolRegistry:
    return register_demo_tools(ToolRegistry())
