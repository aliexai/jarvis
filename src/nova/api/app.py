"""FastAPI application: REST + WebSocket, bound to loopback only."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from nova import __version__
from nova.api.auth import make_guard, token_matches
from nova.api.state import CoreState

WINDOW_ACTIONS = frozenset({"minimize", "toggle-maximize", "close", "start-move"})
WS_UNAUTHORIZED = 4401


class _Sender:
    """Serialises sends so background chat tasks and the receive loop never clash."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._lock = asyncio.Lock()
        self._closed = False

    async def send(self, payload: dict[str, Any]) -> None:
        if self._closed:
            return
        async with self._lock:
            try:
                await self._ws.send_json(payload)
            except Exception:
                self._closed = True

    def close(self) -> None:
        self._closed = True


def _hello_payload(state: CoreState) -> dict[str, Any]:
    return {
        "version": __version__,
        "settings": state.settings.model_dump(mode="json"),
        "budget": state.budget_status(),
        "tools": state.registry.names() if state.registry else [],
        "pricing": {
            "tier": state.settings.pricing.tier,
            "last_checked": state.price_table.last_checked,
            "source": state.price_table.source,
        },
    }


def create_app(state: CoreState, static_dir: Path | None = None) -> FastAPI:
    """Build the FastAPI app for one session."""
    app = FastAPI(title="NOVA Core", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.core = state

    guard = Depends(make_guard(state.token))

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "core": "ready"}

    @app.get("/api/settings", dependencies=[guard])
    async def get_settings() -> dict[str, Any]:
        return state.settings.model_dump(mode="json")

    @app.put("/api/settings", dependencies=[guard])
    async def put_settings(patch: dict[str, Any]) -> dict[str, Any]:
        try:
            state.update_settings(patch)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid settings: {exc}") from exc
        return state.settings.model_dump(mode="json")

    @app.get("/api/secrets", dependencies=[guard])
    async def get_secrets() -> dict[str, Any]:
        return {
            "keyring_available": state.secrets.keyring_available,
            "secrets": state.secret_status(),
        }

    @app.get("/api/diagnostics", dependencies=[guard])
    async def get_diagnostics() -> dict[str, Any]:
        return state.diagnostics()

    @app.get("/api/usage", dependencies=[guard])
    async def get_usage() -> dict[str, Any]:
        return {
            "budget": state.budget_status(),
            "recent": state.usage.recent(50) if state.usage else [],
            "pricing": {
                "tier": state.settings.pricing.tier,
                "last_checked": state.price_table.last_checked,
                "source": state.price_table.source,
            },
        }

    @app.get("/api/conversations", dependencies=[guard])
    async def list_conversations() -> dict[str, Any]:
        return {"conversations": state.store.list_conversations() if state.store else []}

    @app.get("/api/conversations/{conversation_id}/messages", dependencies=[guard])
    async def conversation_messages(conversation_id: str) -> dict[str, Any]:
        if state.store is None:
            return {"messages": []}
        rows = state.store.recent_messages(conversation_id, 200)
        return {
            "messages": [
                {
                    "id": row.id,
                    "role": row.role,
                    "content": row.content,
                    "model": row.model,
                    "created_at": row.created_at,
                    "cost_usd": row.cost_usd,
                    "tool_name": row.tool_name,
                    "tool_result": row.tool_result,
                    "error_kind": row.error_kind,
                    "local": row.local,
                }
                for row in rows
            ]
        }

    @app.post("/api/provider/test", dependencies=[guard])
    async def provider_test(model: str | None = None) -> dict[str, Any]:
        target = model or state.settings.models.fast
        provider = state.provider()
        result = await provider.test_connection(target)
        if state.audit is not None:
            state.audit.append(
                "user",
                "provider.test",
                target=target,
                decision="allow" if result.ok else "deny",
                detail=f"{result.latency_ms}ms",
            )
        return {
            "ok": result.ok,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "detail": result.detail,
        }

    @app.post("/api/privacy/acknowledge", dependencies=[guard])
    async def privacy_acknowledge() -> dict[str, Any]:
        state.update_settings({"privacy": {"notice_acknowledged": True}})
        return state.settings.model_dump(mode="json")

    @app.post("/api/window/{action}", dependencies=[guard])
    async def window_action(action: str) -> dict[str, Any]:
        if action not in WINDOW_ACTIONS:
            raise HTTPException(status_code=400, detail=f"unknown window action: {action}")
        if state.window_action is None:
            raise HTTPException(status_code=503, detail="no window attached")
        state.window_action(action)
        return {"ok": True, "action": action}

    @app.post("/api/ui/ready", dependencies=[guard])
    async def ui_ready() -> dict[str, Any]:
        state.ui_ready.set()
        state.log.info("UI reported ready")
        return {"ok": True}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        if not token_matches(websocket.query_params.get("token"), state.token):
            await websocket.close(code=WS_UNAUTHORIZED)
            return

        await websocket.accept()
        sender = _Sender(websocket)
        await sender.send({"type": "hello", "data": _hello_payload(state)})

        tasks: set[asyncio.Task] = set()
        current: dict[str, asyncio.Task | None] = {"chat": None}

        def finish(task: asyncio.Task) -> None:
            tasks.discard(task)
            if current["chat"] is task:
                current["chat"] = None
            if task.cancelled():
                return
            error = task.exception()
            if error is not None:
                state.log.error("chat task failed: %s", error)

        async def handle(message: dict) -> None:
            kind = message.get("type")

            if kind == "ping":
                await sender.send({"type": "pong"})
                return

            if kind == "chat.send":
                running = current["chat"]
                if running is not None and not running.done():
                    await sender.send(
                        {
                            "type": "chat.error",
                            "data": {"kind": "busy", "message": "A reply is still streaming."},
                        }
                    )
                    return
                text = str(message.get("text") or "").strip()
                if not text:
                    await sender.send(
                        {
                            "type": "chat.error",
                            "data": {"kind": "empty", "message": "Empty message."},
                        }
                    )
                    return
                if state.chat is None:
                    await sender.send(
                        {
                            "type": "chat.error",
                            "data": {"kind": "unavailable", "message": "Chat is not available."},
                        }
                    )
                    return

                task = asyncio.create_task(
                    state.chat.handle(
                        text,
                        conversation_id=message.get("conversation_id"),
                        emit=sender.send,
                        model_override=message.get("model"),
                    )
                )
                current["chat"] = task
                tasks.add(task)
                task.add_done_callback(finish)
                return

            if kind == "chat.cancel":
                running = current["chat"]
                if running is not None and not running.done():
                    running.cancel()
                await sender.send({"type": "chat.done", "data": {"aborted": True}})
                return

            if kind == "settings.update":
                patch = message.get("patch") or {}
                try:
                    state.update_settings(patch)
                except Exception as exc:
                    await sender.send({"type": "settings.error", "data": {"message": str(exc)}})
                    return
                await sender.send(
                    {"type": "settings", "data": state.settings.model_dump(mode="json")}
                )
                await sender.send({"type": "budget", "data": state.budget_status()})
                return

            await sender.send(
                {"type": "error", "data": {"message": f"unknown message type: {kind!r}"}}
            )

        try:
            while True:
                payload = await websocket.receive_json()
                await handle(payload)
        except WebSocketDisconnect:
            state.log.info("UI websocket disconnected")
        except Exception:
            state.log.exception("websocket error")
        finally:
            sender.close()
            for task in list(tasks):
                task.cancel()

    if static_dir is not None and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
    else:

        @app.get("/")
        async def missing_ui() -> dict[str, Any]:
            return {
                "error": "UI bundle not found",
                "hint": "cd ui/web && npm install --include=dev && npm run build",
            }

    return app
