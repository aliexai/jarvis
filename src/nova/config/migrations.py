"""Settings-file migrations.

The settings file carries a ``version`` integer. On load, :func:`migrate`
brings any older document up to :data:`SCHEMA_VERSION` by applying the
registered step functions in order. This keeps upgrades safe: a file written by
an older build never crashes a newer one.

To add a migration, bump :data:`SCHEMA_VERSION` and register a function for the
*previous* version, e.g. ``_MIGRATIONS[1] = _v1_to_v2``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def migrate(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return ``raw`` upgraded to the current schema version.

    A document with no ``version`` is treated as version 0.
    """
    data: dict[str, Any] = dict(raw or {})
    version = int(data.get("version", 0) or 0)

    guard = 0
    while version < SCHEMA_VERSION:
        guard += 1
        if guard > 100:  # pragma: no cover - defensive, cannot happen normally
            raise RuntimeError("migration did not converge")
        step = _MIGRATIONS.get(version)
        if step is None:
            version += 1
            continue
        data = step(data)
        version = int(data.get("version", version + 1))

    data["version"] = SCHEMA_VERSION
    return data
