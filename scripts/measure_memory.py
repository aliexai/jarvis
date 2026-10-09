"""Measure NOVA's idle resident memory.

Launches the app, lets the UI settle, then reports resident memory for the
process tree plus any QtWebEngine helper that is not parented to it. This is a
development/verification tool (see the performance report).

Usage:
    python scripts/measure_memory.py --seconds 12 --out artifacts/memory.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
NOVA = ROOT / ".venv" / "Scripts" / "nova.exe"


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure NOVA idle memory")
    parser.add_argument("--seconds", type=float, default=12.0, help="settle time before measuring")
    parser.add_argument("--out", default=None, help="write the JSON report to this path")
    parser.add_argument("--exe", default=str(NOVA), help="path to the nova launcher")
    args = parser.parse_args()

    launcher = Path(args.exe)
    if not launcher.exists():
        print(f"nova launcher not found at {launcher}", file=sys.stderr)
        return 1

    process = subprocess.Popen(
        [str(launcher), "ui"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        time.sleep(max(1.0, args.seconds))

        root = psutil.Process(process.pid)
        rows: list[dict] = []
        total = 0
        seen: set[int] = set()

        for member in [root, *root.children(recursive=True)]:
            try:
                rss = member.memory_info().rss
                name = member.name()
            except Exception:
                continue
            seen.add(member.pid)
            total += rss
            rows.append({"pid": member.pid, "name": name, "rss_mb": round(rss / 1048576, 1)})

        # Include any QtWebEngine helper that is not a descendant of the launcher.
        for candidate in psutil.process_iter(["name", "memory_info"]):
            try:
                name = candidate.info.get("name") or ""
                info = candidate.info.get("memory_info")
                if "QtWebEngine" in name and info is not None and candidate.pid not in seen:
                    seen.add(candidate.pid)
                    total += info.rss
                    rows.append(
                        {
                            "pid": candidate.pid,
                            "name": name,
                            "rss_mb": round(info.rss / 1048576, 1),
                            "unparented": True,
                        }
                    )
            except Exception:
                continue

        report = {
            "resident_mb": round(total / 1048576, 1),
            "processes": len(rows),
            "breakdown": rows,
        }
        print(json.dumps(report, indent=2))
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
