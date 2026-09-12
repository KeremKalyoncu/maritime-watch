"""Kinematic Closest Point of Approach (CPA) and Time to CPA (TCPA) engine.
Detects collision risk between moving commercial vessels using Cartesian
decomposition of AIS velocity vectors.
"""

from __future__ import annotations

import math
from typing import Any

from src.model import (
    CpaEvent,
    Incident,
    IncidentType,
    Severity,
    Source,
    Status,
    Vessel,
    now_iso,
)

# Standard maritime thresholds
DEFAULT_CPA_LIMIT_NM = 0.35      # ~650 meters
DEFAULT_TCPA_LIMIT_MIN = 12.0     # 12 minutes
MIN_UNDERWAY_SPEED_KN = 3.0       # Ignore slow-drifting / maneuvering craft
MAX_COARSE_DISTANCE_NM = 3.0      # Coarse pre-filter to avoid O(N^2) load


def calculate_cpa(p1: dict[str, Any], p2: dict[str, Any]) -> tuple[float, float] | None:
    """Calculate (CPA_NM, TCPA_MINUTES) between two vessels.

    Returns None if:
    - Distance > MAX_COARSE_DISTANCE_NM
    - Vessels are diverging (TCPA <= 0)
    - Relative velocity is virtually zero (parallel same-speed)
    - Missing required navigation fields
    """
    try:
        lat1, lon1 = float(p1["lat"]), float(p1["lon"])
        lat2, lon2 = float(p2["lat"]), float(p2["lon"])
        sog1, cog1 = float(p1.get("sog") or 0.0), float(p1.get("cog") or 0.0)
        sog2, cog2 = float(p2.get("sog") or 0.0), float(p2.get("cog") or 0.0)
    except (KeyError, ValueError, TypeError):
        return None

    # Cartesian coordinate difference in Nautical Miles
    mean_lat_rad = math.radians((lat1 + lat2) / 2.0)
    dy = (lat2 - lat1) * 60.0                                 # North-South distance in NM
    dx = (lon2 - lon1) * 60.0 * math.cos(mean_lat_rad)        # East-West distance in NM

    d0 = math.sqrt(dx * dx + dy * dy)
    if d0 > MAX_COARSE_DISTANCE_NM or d0 < 0.001:
        return None

    # Velocity vectors in knots (nautical miles per hour)
    # Maritime COG: 0 deg = North (+y), 90 deg = East (+x)
    rad_cog1 = math.radians(cog1)
    rad_cog2 = math.radians(cog2)

    v1x = sog1 * math.sin(rad_cog1)
    v1y = sog1 * math.cos(rad_cog1)

    v2x = sog2 * math.sin(rad_cog2)
    v2y = sog2 * math.cos(rad_cog2)

    # Relative velocity of vessel 2 with respect to vessel 1
    v_rel_x = v2x - v1x
    v_rel_y = v2y - v1y

    v_rel_sq = v_rel_x * v_rel_x + v_rel_y * v_rel_y
    if v_rel_sq < 1e-6:
        # Zero relative velocity: same speed and heading, distance will remain constant
        return None

    # Relative position vector dot relative velocity vector
    r_dot_v = dx * v_rel_x + dy * v_rel_y

    # Time to Closest Point of Approach in hours
    tcpa_hours = -r_dot_v / v_rel_sq
    tcpa_min = tcpa_hours * 60.0

    # If TCPA <= 0, vessels have already passed closest point and are moving apart
    if tcpa_min <= 0.0:
        return None

    # Position vector at closest approach
    cpa_x = dx + v_rel_x * tcpa_hours
    cpa_y = dy + v_rel_y * tcpa_hours
    cpa_nm = math.sqrt(cpa_x * cpa_x + cpa_y * cpa_y)

    return (round(cpa_nm, 3), round(tcpa_min, 1))


def is_vessel_underway(p: dict[str, Any]) -> bool:
    """Filter out anchored, moored or stationary vessels."""
    if p.get("nav_status") in (1, 5):  # 1 = anchored, 5 = moored
        return False
    sog = float(p.get("sog") or 0.0)
    if sog < MIN_UNDERWAY_SPEED_KN:
        return False
    return True


def detect_cpa_risks(
    positions: list[dict[str, Any]],
    cpa_limit_nm: float = DEFAULT_CPA_LIMIT_NM,
    tcpa_limit_min: float = DEFAULT_TCPA_LIMIT_MIN,
) -> list[CpaEvent]:
    """Scan position reports and return detected high-risk close-quarter encounters."""
    # Pre-filter underway candidates with valid positions
    candidates: list[dict[str, Any]] = []
    for p in positions:
        if p.get("msg_type") == "safety":
            continue
        if p.get("mmsi") is None or p.get("lat") is None or p.get("lon") is None:
            continue
        if not is_vessel_underway(p):
            continue
        candidates.append(p)

    events: list[CpaEvent] = []
    n = len(candidates)

    for i in range(n):
        p1 = candidates[i]
        for j in range(i + 1, n):
            p2 = candidates[j]
            res = calculate_cpa(p1, p2)
            if res is None:
                continue
            cpa_nm, tcpa_min = res
            if cpa_nm < cpa_limit_nm and 0 < tcpa_min <= tcpa_limit_min:
                mmsi1 = int(p1["mmsi"])
                mmsi2 = int(p2["mmsi"])
                mean_lat = (float(p1["lat"]) + float(p2["lat"])) / 2.0
                mean_lon = (float(p1["lon"]) + float(p2["lon"])) / 2.0

                event = CpaEvent(
                    mmsi1=mmsi1,
                    mmsi2=mmsi2,
                    cpa_nm=cpa_nm,
                    tcpa_min=tcpa_min,
                    lat=round(mean_lat, 4),
                    lon=round(mean_lon, 4),
                    sog1_kn=round(float(p1.get("sog") or 0.0), 1),
                    sog2_kn=round(float(p2.get("sog") or 0.0), 1),
                    vessel1_name=p1.get("name") or str(mmsi1),
                    vessel2_name=p2.get("name") or str(mmsi2),
                    ts=now_iso(),
                )
                events.append(event)

    return events


def cpa_events_to_incidents(events: list[CpaEvent]) -> list[Incident]:
    """Convert CpaEvents into standard Incident models for storage and mapping."""
    incidents: list[Incident] = []
    for ev in events:
        min_m = min(ev.mmsi1, ev.mmsi2)
        max_m = max(ev.mmsi1, ev.mmsi2)
        stable_id = f"cpa-{min_m}-{max_m}"

        name_pair = f"{ev.vessel1_name} & {ev.vessel2_name}"
        detail_msg = (
            f"Çatışma / Yakın Geçiş Riski: CPA {ev.cpa_nm:.2f} NM (~{int(ev.cpa_nm * 1852)} m), "
            f"kalan süre: {ev.tcpa_min:.1f} dk (Hızlar: {ev.sog1_kn:.1f} kn / {ev.sog2_kn:.1f} kn)"
        )

        inc = Incident(
            id=stable_id,
            type=IncidentType.COLLISION_RISK.value,
            status=Status.PROBABLE.value,
            confidence=0.85,
            severity=Severity.MAJOR.value,
            lat=ev.lat,
            lon=ev.lon,
            vessel=Vessel(name=name_pair, mmsi=ev.mmsi1),
            notes=[detail_msg],
        )
        inc.add_source(Source(
            kind="ais-cpa",
            org="AIS",
            detail=detail_msg,
            ts=ev.ts,
        ))
        incidents.append(inc)

    return incidents
