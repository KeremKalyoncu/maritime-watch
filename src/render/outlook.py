"""Publish go/no-go hour windows for the web map and Telegram bot.

Cycle writes web/data/outlook.json once; consumers read the file instead of
re-fetching Open-Meteo (important on the Note 4 edge host).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.ingest import _net
from src.ingest.openmeteo import fetch_forecast_points
from src.model import now_iso
from src.process.window import area_to_public_dict
from src.process.window import build as build_window

BOAT_CLASS_IDS = ("small", "medium", "large")


def render_outlook(
    cfg: dict,
    out_file: str | Path | None = None,
    points: list[dict] | None = None,
) -> dict[str, Any] | None:
    """Build OutlookFile v1. Returns None when nothing safe to publish."""
    oc = cfg.get("outlook") or {}
    if not oc.get("enabled", True):
        print("[outlook:warn] disabled in config — skip write")
        return None

    try:
        pts = points if points is not None else fetch_forecast_points(cfg)
    except Exception as e:
        print(f"[outlook:error] forecast fetch failed: {e}")
        return None

    if not pts:
        print("[outlook:warn] no live forecast points — skip write")
        return None

    if points is None and any(_net.STATUS.get(k) == "sample" for k in _net.STATUS if "openmeteo" in k):
        print("[outlook:warn] refusing sample-backed outlook")
        return None

    hours = int(oc.get("hours", 18))
    tz = float(oc.get("tz_offset_hours", 3))
    classes_cfg = oc.get("classes") or {}

    classes_out: dict[str, Any] = {}
    for cid in BOAT_CLASS_IDS:
        klass = classes_cfg.get(cid) or {}
        if not klass:
            continue
        limits = {
            "label": klass.get("label", cid),
            "gust_kn": float(klass.get("gust_kn", 34)),
            "wave_m": float(klass.get("wave_m", 2.0)),
        }
        areas = []
        for p in pts:
            name = (p.get("name") or "").strip()
            if not name:
                continue
            area = build_window(
                name,
                p.get("times") or [],
                p.get("gusts") or [],
                p.get("waves") or [],
                limits,
                hours=hours,
                tz_offset_h=tz,
                lat=p.get("lat"),
                lon=p.get("lon"),
                wave_periods=p.get("wave_periods"),
                wind_dirs=p.get("wind_dirs"),
                visibilities=p.get("visibilities"),
            )
            areas.append(area_to_public_dict(area))
        classes_out[cid] = {
            "label": klass.get("label", cid),
            "limits": limits,
            "areas": areas,
        }

    if len(classes_out) < 3:
        print("[outlook:error] schema validation failed: missing boat classes")
        return None

    expected_names = [
        (p.get("name") or "").strip()
        for p in (cfg.get("openmeteo") or {}).get("points") or []
        if (p.get("name") or "").strip()
    ]
    present_names = sorted(
        {a.get("name") for block in classes_out.values() for a in (block.get("areas") or []) if a.get("name")}
    )
    missing = [n for n in expected_names if n not in set(present_names)]
    coverage = {
        "expected": len(expected_names),
        "present": len(present_names),
        "missing": missing,
    }
    if missing:
        print(
            f"[outlook] coverage present={len(present_names)}/{len(expected_names)} "
            f"missing={', '.join(missing)}"
        )

    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated": now_iso(),
        "hours": hours,
        "tz_offset_hours": tz,
        "question": "today",
        "coverage": coverage,
        "classes": classes_out,
    }

    if out_file:
        path = Path(out_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(payload, ensure_ascii=False, indent=2)
            if len(raw.encode("utf-8")) > 256_000:
                print("[outlook:error] payload too large — skip write")
                return None
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(raw, encoding="utf-8")
            tmp.replace(path)
            print(f"[outlook] wrote {path} bytes={len(raw.encode('utf-8'))}")
        except Exception as e:
            print(f"[outlook:error] write failed: {e}")
            return None

    return payload
