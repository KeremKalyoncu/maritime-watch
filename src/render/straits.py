"""Evaluates and renders live Turkish Straits (Bosphorus & Dardanelles) transit status.
Output: web/data/straits.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.model import StraitStatus, now_iso

STRAIT_ZONES = {
    "bosphorus": {
        "id": "bosphorus",
        "name": "İstanbul Boğazı",
        "lat_min": 41.00, "lat_max": 41.25,
        "lon_min": 28.98, "lon_max": 29.15,
    },
    "dardanelles": {
        "id": "dardanelles",
        "name": "Çanakkale Boğazı",
        "lat_min": 40.05, "lat_max": 40.40,
        "lon_min": 26.15, "lon_max": 26.70,
    },
}


def evaluate_strait(
    strait_id: str,
    warnings: list[Any],
    vessels_data: dict[str, Any] | None = None,
) -> StraitStatus:
    zone = STRAIT_ZONES[strait_id]
    name = zone["name"]

    # 1. Check for official suspensions or severe low visibility/fog
    is_suspended = False
    suspension_reason = None

    for w in warnings:
        area_low = (w.area or "").lower()
        head_low = (w.headline or "").lower()
        if strait_id in area_low or name.lower() in area_low or name.lower() in head_low:
            if "askı" in head_low or "kapat" in head_low or "durdur" in head_low:
                is_suspended = True
                suspension_reason = "Resmi Geçiş Kısıtlaması / Kaza Operasyonu"
                break
            if w.kind in ("fog", "metar") and ("sis" in head_low or "fog" in head_low or "görüş" in head_low):
                is_suspended = True
                suspension_reason = "Yoğun Sis (Görüş < 300m)"
                break

    # 2. Check AIS traffic in strait corridor
    in_transit_count = 0
    speeds: list[float] = []

    if vessels_data:
        for _mmsi, v in vessels_data.items():
            track = v.get("track", [])
            if not track:
                continue
            last = track[-1]
            lat, lon = last.get("lat"), last.get("lon")
            if lat is None or lon is None:
                continue
            if zone["lat_min"] <= lat <= zone["lat_max"] and zone["lon_min"] <= lon <= zone["lon_max"]:
                sog = float(last.get("sog") or 0.0)
                if sog >= 0.8:  # underway in strait
                    in_transit_count += 1
                    speeds.append(sog)

    avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 8.5

    if is_suspended:
        status = "suspended"
        status_tr = "Geçiş Askıya Alındı"
    elif in_transit_count >= 6 and avg_speed < 2.5:
        status = "caution"
        status_tr = "Tedbirli Geçiş"
        suspension_reason = "Trafik Yoğunluğu / Yavaş İlerleme"
    else:
        status = "open"
        status_tr = "Trafik Normal"
        suspension_reason = None

    return StraitStatus(
        id=strait_id,
        name=name,
        status=status,
        status_tr=status_tr,
        reason=suspension_reason,
        active_vessels_in_transit=in_transit_count,
        avg_speed_kn=avg_speed,
        last_update=now_iso(),
    )


def render_straits_status(
    store: Any,
    out_file: str | Path | None = None,
    vessels_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_warns = store.active_warnings() if store else []
    bosphorus = evaluate_strait("bosphorus", active_warns, vessels_data)
    dardanelles = evaluate_strait("dardanelles", active_warns, vessels_data)

    payload = {
        "generated": now_iso(),
        "straits": [
            bosphorus.to_dict(),
            dardanelles.to_dict(),
        ],
    }

    if out_file:
        out_path = Path(out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload
