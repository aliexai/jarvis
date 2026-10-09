"""Executes model-requested tool calls.

Every call passes through three gates before the handler runs:

1. the tool must be registered;
2. the arguments must satisfy the tool's JSON schema;
3. the policy engine must allow the tool's declared permission.

Nothing runs on a refusal, and the result always carries a status the UI can
show.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from dataclasses import dataclass, field
from typing import Any

from nova.logging_setup import get_logger
from nova.providers.base import ToolCall
from nova.security.policy import Decision, PolicyEngine
from nova.tools.registry import ToolRegistry
from nova.validation import validate

MAX_DETAIL_CHARS = 2000

STATUS_OK = "ok"
STATUS_DENIED = "denied"
STATUS_INVALID = "invalid"
STATUS_UNKNOWN = "unknown"
STATUS_ERROR = "error"


@dataclass
class ToolResult:
    name: str
    status: str
    detail: str
    args: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    @property
    def args_summary(self) -> str:
        """A compact, single-line rendering of the arguments for the UI."""
        if not self.args:
            return "—"
        text = json.dumps(self.args, ensure_ascii=False)
        return text if len(text) <= 120 else text[:117] + "..."


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, policy: PolicyEngine) -> None:
        self._registry = registry
        self._policy = policy
        self._log = get_logger("tools")

    async def execute(self, call: ToolCall) -> ToolResult:
        started = time.perf_counter()
        tool = self._registry.get(call.name)

        if tool is None:
            return ToolResult(
                name=call.name,
                status=STATUS_UNKNOWN,
                detail=f"no such tool: {call.name}",
                args=call.args,
                duration_ms=_elapsed(started),
            )

        args = call.args if isinstance(call.args, dict) else {}
        errors = validate(args, tool.parameters)
        if errors:
            self._log.warning("tool %s rejected invalid arguments", call.name)
            return ToolResult(
                name=call.name,
                status=STATUS_INVALID,
                detail="; ".join(errors[:5]),
                args=args,
                duration_ms=_elapsed(started),
            )

        if tool.permission is not None:
            decision = self._policy.check(tool.permission)
            if decision.decision is Decision.DENY:
                self._log.warning("tool %s denied by policy: %s", call.name, decision.reason)
                return ToolResult(
                    name=call.name,
                    status=STATUS_DENIED,
                    detail=f"blocked by policy: {decision.reason}",
                    args=args,
                    duration_ms=_elapsed(started),
                )
            if decision.decision is Decision.ASK:
                return ToolResult(
                    name=call.name,
                    status=STATUS_DENIED,
                    detail=f"requires confirmation: {decision.reason}",
                    args=args,
                    duration_ms=_elapsed(started),
                )

        try:
            output = tool.handler(args)
            if inspect.isawaitable(output):
                output = await asyncio.wait_for(output, timeout=tool.timeout_seconds)
            detail = _truncate(str(output))
            return ToolResult(
                name=call.name,
                status=STATUS_OK,
                detail=detail,
                args=args,
                duration_ms=_elapsed(started),
            )
        except TimeoutError:
            return ToolResult(
                name=call.name,
                status=STATUS_ERROR,
                detail="tool timed out",
                args=args,
                duration_ms=_elapsed(started),
            )
        except Exception as exc:
            self._log.exception("tool %s failed", call.name)
            return ToolResult(
                name=call.name,
                status=STATUS_ERROR,
                detail=f"tool failed: {type(exc).__name__}",
                args=args,
                duration_ms=_elapsed(started),
            )


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _truncate(text: str) -> str:
    return text if len(text) <= MAX_DETAIL_CHARS else text[: MAX_DETAIL_CHARS - 3] + "..."
