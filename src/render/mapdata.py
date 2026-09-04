"""Small summary.json alongside the map data (counts + last generated time)."""

from __future__ import annotations

import json
import time
from pathlib import Path


def write_summary(store, out_dir: str, stale_hours: float = 2) -> None:
    incs = store.active_incidents()
    by_status: dict[str, int] = {}
    for i in incs:
        by_status[i.status] = by_status.get(i.status, 0) + 1
    summary = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stale_hours": stale_hours,
        "incident_count": len(incs),
        "by_status": by_status,
        "warning_count": len(store.active_warnings()),
    }
    (Path(out_dir) / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
