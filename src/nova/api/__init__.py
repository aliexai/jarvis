"""Local-only API surface (FastAPI + WebSocket).

Bound to 127.0.0.1 with a random per-session token. Nothing here is exposed
beyond loopback.
"""

from __future__ import annotations

from nova.api.app import create_app
from nova.api.server import CoreServer
from nova.api.state import CoreState

__all__ = ["CoreServer", "CoreState", "create_app"]
