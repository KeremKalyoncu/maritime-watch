"""Coastal earthquakes from several providers (AFAD, USGS, EMSC).

Each provider yields its own Warning; the store's `same_hazard` merge then folds
the same quake reported by two agencies into one item that lists both. Only
quakes near the coast, at/above `min_mag`, in the last `hours_back` hours are kept.
"""

from __future__ import annotations

import time

from ..model import Warning, now_iso
from ..process.classify import nearest_port
from ._net import get_json

AFAD = "https://deprem.afad.gov.tr/apiv2/event/filter"
USGS = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
EMSC = "https://www.seismicportal.eu/fdsnws/event/1/query"

COASTAL_NM = 60
_SEA_WORDS = ("deniz", "körfez", "açık", "boğaz", "ada", "sea", "gulf", "aegean", "marmara")


def _coastal(lat, lon, place: str) -> bool:
    if any(w in place.lower() for w in _SEA_WORDS):
        return True
    np = nearest_port(lat, lon)
    return np is not None and np[1] <= COASTAL_NM


def _bbox(lat, lon, b) -> bool:
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]


def _mk(lat, lon, mag, place, ts, org, url) -> Warning:
    return Warning(
        id=f"eq-{org.lower()}-{round(lat, 2)}-{round(lon, 2)}-{str(ts)[:16]}",
        headline=f"Deprem M{mag:.1f} - {place}",
        area=place, kind="earthquake",
        severity="major" if mag >= 4.5 else "minor",
        org=org, url=url, issued=str(ts), value=round(mag, 1),
        lat=lat, lon=lon,
    )


def _afad(cfg) -> list[Warning]:
    q, bbox = cfg["quakes"], cfg["region"]["bbox"]
    start = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - q["hours_back"] * 3600))
    end = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    url = (f"{AFAD}?start={start.replace(' ', '%20')}&end={end.replace(' ', '%20')}"
           f"&orderby=timedesc&minmag={q['min_mag']}")
    data, _l = get_json(url, "afad_quakes.json")
    out = []
    for ev in data or []:
        try:
            lat, lon, mag = float(ev["latitude"]), float(ev["longitude"]), float(ev["magnitude"])
        except (TypeError, ValueError, KeyError):
            continue
        place = ev.get("location") or "bilinmeyen konum"
        if mag >= q["min_mag"] and _bbox(lat, lon, bbox) and _coastal(lat, lon, place):
            out.append(_mk(lat, lon, mag, place, ev.get("date") or now_iso(),
                           "AFAD", "https://deprem.afad.gov.tr/"))
    return out


def _usgs(cfg) -> list[Warning]:
    q, bbox = cfg["quakes"], cfg["region"]["bbox"]
    data, _l = get_json(USGS, "usgs_quakes.json")
    out = []
    for f in (data or {}).get("features", []):
        p = f.get("properties") or {}
        g = (f.get("geometry") or {}).get("coordinates") or [None, None]
        try:
            lon, lat, mag = float(g[0]), float(g[1]), float(p.get("mag"))
        except (TypeError, ValueError):
            continue
        place = p.get("place") or "unknown"
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime((p.get("time") or 0) / 1000))
        if mag >= q["min_mag"] and _bbox(lat, lon, bbox) and _coastal(lat, lon, place):
            out.append(_mk(lat, lon, mag, place, ts, "USGS", p.get("url") or "https://earthquake.usgs.gov/"))
    return out


def _emsc(cfg) -> list[Warning]:
    q, bbox = cfg["quakes"], cfg["region"]["bbox"]
    start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - q["hours_back"] * 3600))
    url = (f"{EMSC}?format=json&limit=80&minmag={q['min_mag']}&start={start}"
           f"&minlat={bbox['lat_min']}&maxlat={bbox['lat_max']}"
           f"&minlon={bbox['lon_min']}&maxlon={bbox['lon_max']}")
    data, _l = get_json(url, "emsc_quakes.json")
    out = []
    for f in (data or {}).get("features", []):
        p = f.get("properties") or {}
        g = (f.get("geometry") or {}).get("coordinates") or [None, None]
        try:
            lon, lat, mag = float(g[0]), float(g[1]), float(p.get("mag"))
        except (TypeError, ValueError):
            continue
        place = p.get("flynn_region") or "unknown"
        if mag >= q["min_mag"] and _bbox(lat, lon, bbox) and _coastal(lat, lon, place):
            out.append(_mk(lat, lon, mag, place, p.get("time") or now_iso(),
                           "EMSC", "https://www.seismicportal.eu/"))
    return out


def fetch_quakes(cfg: dict) -> list[Warning]:
    out: list[Warning] = []
    for fn in (_afad, _usgs, _emsc):
        try:
            out += fn(cfg)
        except Exception as e:
            print(f"[quakes] {fn.__name__} error: {e}")
    return out[:30]
