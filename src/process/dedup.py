"""Correlate a candidate incident with existing ones (same place + time window)."""

from __future__ import annotations

import math

from ..model import Incident


def dist_nm(a_lat, a_lon, b_lat, b_lon) -> float:
    if None in (a_lat, a_lon, b_lat, b_lon):
        return 9_999.0
    R = 3440.065  # nautical miles
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dlat = math.radians(b_lat - a_lat)
    dlon = math.radians(b_lon - a_lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


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
