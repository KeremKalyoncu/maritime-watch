"""Natural events from NASA EONET (free, no key): storms, wildfires, floods.

Kept when the event's latest point falls inside the region bbox.
"""

from __future__ import annotations

from ..model import Warning, now_iso
from ._net import get_json

API = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=7"

_CAT_TR = {
    "severeStorms": "şiddetli fırtına", "wildfires": "orman yangını",
    "floods": "sel", "volcanoes": "volkan", "seaLakeIce": "deniz buzu",
}


def _bbox(lat, lon, b) -> bool:
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]


def fetch_eonet(cfg: dict) -> list[Warning]:
    bbox = cfg["region"]["bbox"]
    data, _live = get_json(API, "eonet.json")
    out: list[Warning] = []
    for ev in (data or {}).get("events", []):
        geoms = ev.get("geometry") or []
        if not geoms:
            continue
        coords = geoms[-1].get("coordinates")
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not _bbox(lat, lon, bbox):
            continue
        cats = [c.get("id") for c in ev.get("categories", [])]
        cat_tr = next((_CAT_TR[c] for c in cats if c in _CAT_TR), "doğa olayı")
        title = ev.get("title") or cat_tr
        out.append(Warning(
            id=f"eo-{ev.get('id') or abs(hash(title)) % 100000}",
            headline=f"NASA EONET: {cat_tr} - {title[:200]}",
            area=cfg["region"]["name"],
            kind="eonet",
            severity="minor",
            org="NASA EONET",
            url=ev.get("link") or "https://eonet.gsfc.nasa.gov/",
            issued=(geoms[-1].get("date") or now_iso()),
            lat=lat, lon=lon,
        ))
    return out[:15]
