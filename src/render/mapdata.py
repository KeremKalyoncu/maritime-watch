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


def enrich_incident_tracks(store, vessels_data_or_path: str | Path | dict | None = None) -> int:
    """Populate inc.track for active incidents using vessel historical positions.

    Returns the number of incidents enriched.
    """
    vessels: dict = {}
    if isinstance(vessels_data_or_path, dict):
        vessels = vessels_data_or_path
    elif vessels_data_or_path:
        p = Path(vessels_data_or_path)
        if p.exists():
            try:
                vessels = json.loads(p.read_text("utf-8") or "{}")
            except Exception:
                vessels = {}

    if not vessels:
        return 0

    enriched = 0
    for inc in store.active_incidents():
        if not inc.vessel or not inc.vessel.mmsi:
            continue
        v = vessels.get(str(inc.vessel.mmsi))
        if not v:
            continue
        raw_track = v.get("track", [])
        coords: list[list[float]] = []
        for pt in raw_track:
            lat, lon = pt.get("lat"), pt.get("lon")
            if lat is not None and lon is not None:
                coords.append([float(lat), float(lon)])
        if len(coords) >= 2:
            if inc.lat is not None and inc.lon is not None:
                last = coords[-1]
                if abs(last[0] - inc.lat) > 0.0001 or abs(last[1] - inc.lon) > 0.0001:
                    coords.append([round(float(inc.lat), 4), round(float(inc.lon), 4)])
            inc.track = coords
            enriched += 1
    return enriched

