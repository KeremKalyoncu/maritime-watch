"""web/data/stats.json — historical aggregates from the append-only event log.

The live store only keeps about a week (prune), so long-run stats come from
data/events.jsonl instead.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from ..process.dedup import _epoch


def _median(xs: list[float]):
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def build_stats(log_path: str, out_dir: str) -> dict:
    p = Path(log_path)
    latest: dict[str, dict] = {}
    if p.exists():
        for line in p.read_text("utf-8").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not ev.get("kind", "").startswith("incident_"):
                continue
            pl = ev.get("payload") or {}
            iid = pl.get("id")
            if iid:
                latest[iid] = pl

    by_month, by_area, by_type, by_status = Counter(), Counter(), Counter(), Counter()
    vessels = Counter()
    cas_total = cas_count = 0
    resolutions: list[float] = []

    for pl in latest.values():
        first = pl.get("first_seen", "")
        by_month[first[:7] or "?"] += 1
        by_area[pl.get("area") or "belirsiz"] += 1
        by_type[pl.get("type") or "unknown"] += 1
        by_status[pl.get("status") or "signal"] += 1
        v = (pl.get("vessel") or {}).get("name")
        if v:
            vessels[v] += 1
        c = pl.get("casualties")
        if isinstance(c, int) and c > 0:
            cas_total += c
            cas_count += 1
        if pl.get("status") in ("resolved", "false-positive"):
            a, b = _epoch(pl.get("first_seen")), _epoch(pl.get("last_update"))
            if a and b and b >= a:
                resolutions.append((b - a) / 3600.0)

    stats = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_incidents": len(latest),
        "by_month": dict(sorted(by_month.items())),
        "by_area": dict(by_area.most_common()),
        "by_type": dict(by_type.most_common()),
        "by_status": dict(by_status.most_common()),
        "incidents_with_casualties": cas_count,
        "casualties_reported_total": cas_total,
        "top_vessels": vessels.most_common(10),
        "median_resolution_hours": round(_median(resolutions), 1) if resolutions else None,
    }
    (Path(out_dir) / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats
