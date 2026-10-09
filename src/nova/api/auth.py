"""Per-session token authentication for the loopback API."""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable

from fastapi import Header, HTTPException, Query, status


def token_matches(provided: str | None, expected: str) -> bool:
    """Constant-time comparison of a supplied token against the session token."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided, expected)


def make_guard(expected: str) -> Callable[..., Awaitable[None]]:
    """Build a FastAPI dependency that enforces the session token."""

    async def guard(
        token: str | None = Query(default=None),
        x_nova_token: str | None = Header(default=None),
    ) -> None:
        if not token_matches(token or x_nova_token, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing session token",
            )

    return guard
