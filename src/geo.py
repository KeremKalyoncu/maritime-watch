"""Polygon sea areas. Point-in-polygon against web/data/regions.geojson, with a
bounding-box table as the fallback when the GeoJSON is missing.
"""

from __future__ import annotations

import json
from pathlib import Path

_GEOJSON = Path(__file__).resolve().parent.parent / "web" / "data" / "regions.geojson"

# fallback boxes (name, lat_min, lat_max, lon_min, lon_max), most specific first
_BOXES = [
    ("İstanbul Boğazı", 41.00, 41.28, 28.90, 29.20),
    ("Çanakkale Boğazı", 39.95, 40.55, 26.10, 26.75),
    ("Marmara Denizi", 40.30, 41.05, 26.70, 29.95),
    ("Saros Körfezi", 40.30, 40.75, 26.05, 26.75),
    ("Kuzey Ege", 38.90, 40.60, 24.50, 27.20),
    ("Orta Ege", 37.60, 38.90, 24.50, 27.60),
    ("Güney Ege", 36.00, 37.60, 24.50, 28.60),
    ("Gökova Körfezi", 36.85, 37.15, 27.30, 28.35),
    ("Antalya Körfezi", 36.10, 37.00, 29.60, 31.60),
    ("Batı Akdeniz", 35.80, 36.60, 28.60, 30.00),
    ("Mersin–İskenderun Körfezi", 35.80, 37.10, 32.20, 36.60),
    ("Batı Karadeniz", 41.10, 43.60, 27.30, 33.00),
    ("Orta Karadeniz", 41.00, 43.20, 33.00, 37.50),
    ("Doğu Karadeniz", 40.90, 42.60, 37.50, 42.20),
]

_polys: list[tuple[str, list]] = []          # (name, list-of-rings)  ring = [(lon,lat),...]
_centroids: dict[str, tuple[float, float]] = {}


def _load() -> None:
    if _polys or not _GEOJSON.exists():
        return
    try:
        gj = json.loads(_GEOJSON.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for feat in gj.get("features", []):
        name = (feat.get("properties") or {}).get("name")
        geom = feat.get("geometry") or {}
        if not name or geom.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rings = [[(float(x), float(y)) for x, y in poly[0]] for poly in polys if poly and poly[0]]
        if rings:
            _polys.append((name, rings))


def _in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def area_of(lat, lon) -> str:
    if lat is None or lon is None:
        return ""
    _load()
    for name, rings in _polys:
        if any(_in_ring(lon, lat, r) for r in rings):
            return name
    for name, la0, la1, lo0, lo1 in _BOXES:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name
    return "Türk karasuları civarı"


def area_centroid(name: str):
    if not name:
        return None, None
    _load()
    if name in _centroids:
        return _centroids[name]
    low = name.lower()
    for pname, rings in _polys:
        if pname.lower() in low or low in pname.lower():
            pts = rings[0]
            lat = round(sum(p[1] for p in pts) / len(pts), 3)
            lon = round(sum(p[0] for p in pts) / len(pts), 3)
            _centroids[name] = (lat, lon)
            return lat, lon
    for pname, la0, la1, lo0, lo1 in _BOXES:
        if pname.lower() in low or low in pname.lower():
            return round((la0 + la1) / 2, 3), round((lo0 + lo1) / 2, 3)
    return None, None
