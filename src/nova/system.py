"""Local system metrics for the System panel.

Uses :mod:`psutil` when available and degrades to an explicit "unavailable"
result otherwise, so the panel never shows fabricated numbers.
"""

from __future__ import annotations

import os
import shutil
from typing import Any


def _disks() -> list[dict[str, Any]]:
    import psutil

    disks: list[dict[str, Any]] = []
    for partition in psutil.disk_partitions(all=False):
        if not partition.fstype:
            continue
        try:
            usage = shutil.disk_usage(partition.mountpoint)
        except Exception:
            continue
        total = usage.total
        disks.append(
            {
                "mount": partition.mountpoint,
                "total": total,
                "used": usage.used,
                "percent": round(usage.used / total * 100, 1) if total else 0.0,
            }
        )
    return disks


def snapshot() -> dict[str, Any]:
    """Return a point-in-time view of the machine, or an unavailable marker."""
    try:
        import psutil
    except Exception:
        return {"available": False, "reason": "psutil is not installed"}

    data: dict[str, Any] = {"available": True}
    try:
        memory = psutil.virtual_memory()
        data["cpu"] = {
            "percent": psutil.cpu_percent(interval=None),
            "count": psutil.cpu_count(logical=True),
        }
        data["memory"] = {
            "total": memory.total,
            "used": memory.used,
            "percent": memory.percent,
        }
        data["disks"] = _disks()

        battery = None
        try:
            reading = psutil.sensors_battery()
        except Exception:
            reading = None
        if reading is not None:
            battery = {"percent": round(reading.percent, 1), "plugged": bool(reading.power_plugged)}
        data["battery"] = battery

        process = psutil.Process(os.getpid())
        data["nova"] = {
            "rss": process.memory_info().rss,
            "children": len(process.children(recursive=True)),
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"available": False, "reason": str(exc)}
    return data
