"""web/data/health.json — per-source status and cycle timing, for monitoring."""

from __future__ import annotations

import json
import time
from pathlib import Path


def write_health(out_dir: str, records: list[dict], started: float,
                 incidents: int, warnings: int) -> dict:
    ok = sum(1 for r in records if r["ok"])
    down = [r["source"] for r in records if not r["ok"]]
    health = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cycle_seconds": round(time.time() - started, 1),
        "sources_ok": ok,
        "sources_total": len(records),
        "sources_down": down,
        "incidents": incidents,
        "warnings": warnings,
        "sources": {r["source"]: {k: v for k, v in r.items() if k != "source"} for r in records},
    }
    (Path(out_dir) / "health.json").write_text(
        json.dumps(health, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return health
