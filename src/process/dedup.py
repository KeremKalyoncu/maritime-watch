"""Correlate a candidate incident/warning with existing ones (same place + time)."""

from __future__ import annotations

import calendar
import math
import time

from ..model import Incident, Warning


def dist_nm(a_lat, a_lon, b_lat, b_lon) -> float:
    if None in (a_lat, a_lon, b_lat, b_lon):
        return 9_999.0
    R = 3440.065  # nautical miles
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dlat = math.radians(b_lat - a_lat)
    dlon = math.radians(b_lon - a_lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


_TR_LOWER = str.maketrans("İIŞĞÜÖÇ", "iışğüöç")
_BUCKET = {
    "marine-weather": "weather", "metar": "weather",
    "earthquake": "quake",
    "gdacs": "disaster", "eonet": "disaster",
    "nav-warning": "navwarn", "navtex": "navwarn",
}


def _epoch(s):
    if not s:
        return None
    s = str(s).replace("Z", "").split(".")[0].split("+")[0].replace("T", " ").replace(" UTC", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%a, %d %b %Y %H:%M:%S"):
        try:
            return calendar.timegm(time.strptime(s, fmt))
        except ValueError:
            continue
    return None


def _minutes_apart(a, b):
    ea, eb = _epoch(a), _epoch(b)
    if ea is None or eb is None:
        return 0.0
    return abs(ea - eb) / 60.0


def same_hazard(a: Warning, b: Warning) -> bool:
    """True when two warnings describe the same real-world hazard, so they should
    be merged into one item that lists both sources."""
    ba, bb = _BUCKET.get(a.kind), _BUCKET.get(b.kind)
    if ba is None or ba != bb:
        return False
    d = dist_nm(a.lat, a.lon, b.lat, b.lon)
    na = a.area.translate(_TR_LOWER).lower().strip()
    nb = b.area.translate(_TR_LOWER).lower().strip()
    same_area = bool(na) and bool(nb) and (na == nb or na[:6] == nb[:6])
    gap = _minutes_apart(a.issued, b.issued)

    if ba == "quake":
        mag_ok = (a.value is None or b.value is None or abs(a.value - b.value) <= 0.7)
        return d <= 35 and gap <= 5 and mag_ok
    if ba == "weather":
        return (same_area or d <= 45) and gap <= 12 * 60
    # disaster / navwarn
    return (same_area or d <= 70) and gap <= 36 * 60


def correlate(store, candidate: Incident, radius_nm: float = 8.0) -> Incident:
    """If a nearby open incident exists, merge candidate's sources into it and
    return that incident; otherwise return the candidate unchanged."""
    for inc in store.active_incidents():
        if inc.status in ("resolved", "false-positive"):
            continue
        if dist_nm(inc.lat, inc.lon, candidate.lat, candidate.lon) <= radius_nm:
            for s in candidate.sources:
                inc.add_source(s)
            if candidate.vessel.mmsi and not inc.vessel.mmsi:
                inc.vessel = candidate.vessel
            if candidate.casualties is not None:
                inc.casualties = candidate.casualties
            if candidate.type != "unknown" and inc.type == "unknown":
                inc.type = candidate.type
            return inc
    return candidate
