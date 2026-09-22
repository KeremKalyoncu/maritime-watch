"""IMO IAMSAR Standard Leeway Search and Rescue (SAR) Drift Modeling Engine.
Computes projected search datum positions and search radii for distress,
man-overboard, capsize, and drifting incidents.
"""

from __future__ import annotations

import math
from typing import Any

# Empirical Leeway Factors from IMO IAMSAR Manual Volume II
LEEWAY_FACTORS: dict[str, float] = {
    "person_in_water": 0.020,  # 2.0% of 10m wind speed
    "man-overboard": 0.020,
    "liferaft": 0.035,  # 3.5%
    "capsize": 0.030,
    "drift": 0.030,
    "distress": 0.025,
    "default": 0.025,
}


def calculate_leeway_drift(
    lat: float,
    lon: float,
    wind_kn: float,
    wind_dir_from: float,
    current_kn: float = 0.0,
    current_dir_to: float = 0.0,
    hours: float = 1.0,
    target_type: str = "person_in_water",
) -> dict[str, Any]:
    """Calculate projected SAR datum position and search radius after t hours.

    Args:
        lat: Initial latitude
        lon: Initial longitude
        wind_kn: Wind speed in knots (10-meter altitude)
        wind_dir_from: Wind direction in degrees (direction wind blows FROM)
        current_kn: Surface water current in knots
        current_dir_to: Current direction in degrees (direction water flows TOWARDS)
        hours: Drift duration in hours
        target_type: Object type ('person_in_water', 'liferaft', 'capsize', etc.)

    Returns:
        dict with projected datum lat, lon, drift speed, bearing, distance, and search radius.
    """
    factor = LEEWAY_FACTORS.get(target_type.lower(), LEEWAY_FACTORS["default"])

    # 1. Leeway vector: blows in the DOWNWIND direction
    downwind_deg = (wind_dir_from + 180.0) % 360.0
    downwind_rad = math.radians(downwind_deg)
    leeway_speed = factor * max(0.0, wind_kn)

    v_leeway_x = leeway_speed * math.sin(downwind_rad)
    v_leeway_y = leeway_speed * math.cos(downwind_rad)

    # 2. Surface current vector
    curr_rad = math.radians(current_dir_to % 360.0)
    v_curr_x = max(0.0, current_kn) * math.sin(curr_rad)
    v_curr_y = max(0.0, current_kn) * math.cos(curr_rad)

    # 3. Total drift vector (Cartesian summation)
    v_total_x = v_leeway_x + v_curr_x
    v_total_y = v_leeway_y + v_curr_y

    total_drift_speed = math.sqrt(v_total_x * v_total_x + v_total_y * v_total_y)
    drift_bearing = (math.degrees(math.atan2(v_total_x, v_total_y)) + 360.0) % 360.0

    # Total distance drifted over time in nautical miles
    dist_nm = total_drift_speed * max(0.0, hours)

    # Projected coordinates using spherical approximation
    lat_rad = math.radians(lat)
    dy_nm = v_total_y * hours
    dx_nm = v_total_x * hours

    d_lat = dy_nm / 60.0
    cos_lat = math.cos(lat_rad)
    d_lon = (dx_nm / (60.0 * cos_lat)) if abs(cos_lat) > 1e-6 else 0.0

    proj_lat = round(lat + d_lat, 5)
    proj_lon = round(lon + d_lon, 5)

    # Search radius (IAMSAR formula: Initial position error + Leeway divergence uncertainty)
    # X = 0.5 NM (typical maritime GPS/reporting uncertainty)
    # Drift uncertainty = 0.3 * total drift distance
    search_radius_nm = round(0.5 + (0.30 * dist_nm), 2)

    return {
        "hours": round(hours, 1),
        "lat": proj_lat,
        "lon": proj_lon,
        "drift_speed_kn": round(total_drift_speed, 2),
        "drift_bearing_deg": round(drift_bearing, 1),
        "drift_distance_nm": round(dist_nm, 2),
        "search_radius_nm": search_radius_nm,
        "target_type": target_type,
    }


def predict_sar_drift_trajectory(
    lat: float,
    lon: float,
    wind_kn: float,
    wind_dir_from: float,
    current_kn: float = 0.0,
    current_dir_to: float = 0.0,
    intervals: tuple[float, ...] = (1.0, 3.0, 6.0),
    target_type: str = "person_in_water",
) -> dict[str, Any]:
    """Generate multi-interval SAR drift projection (1h, 3h, 6h)."""
    projections = [
        calculate_leeway_drift(
            lat=lat,
            lon=lon,
            wind_kn=wind_kn,
            wind_dir_from=wind_dir_from,
            current_kn=current_kn,
            current_dir_to=current_dir_to,
            hours=h,
            target_type=target_type,
        )
        for h in intervals
    ]

    return {
        "initial_position": {"lat": lat, "lon": lon},
        "target_type": target_type,
        "wind_kn": round(wind_kn, 1),
        "wind_dir": round(wind_dir_from, 1),
        "current_kn": round(current_kn, 1),
        "projections": projections,
    }


def enrich_sar_drift(inc: Any, weather_points: list[dict] | None = None) -> None:
    """Enrich active SAR-applicable incidents with Leeway drift modeling."""
    sar_types = {"man-overboard", "distress", "capsize", "drift"}
    if getattr(inc, "type", "") not in sar_types:
        return
    if inc.lat is None or inc.lon is None:
        return

    # Extract wind and current from weather_context or closest weather point
    wind_kn = 10.0
    wind_dir = 0.0
    current_kn = 0.0
    current_dir = 0.0

    wc = getattr(inc, "weather_context", None)
    if wc:
        wind_kn = float(getattr(wc, "wind_kn", 10.0) or 10.0)
        wind_dir = float(getattr(wc, "wind_dir", 0) or 0.0)
        current_kn = float(getattr(wc, "current_kn", 0.0) or 0.0)
        current_dir = (wind_dir + 180.0) % 360.0  # approximate current setting
    elif weather_points:
        # Find nearest point
        best_pt = None
        best_dist = float("inf")
        for pt in weather_points:
            try:
                plat, plon = float(pt["lat"]), float(pt["lon"])
                d = math.hypot((plat - inc.lat) * 60.0, (plon - inc.lon) * 60.0 * math.cos(math.radians(inc.lat)))
                if d < best_dist:
                    best_dist = d
                    best_pt = pt
            except Exception:
                continue
        if best_pt and best_dist <= 40.0:
            wind_kn = float(best_pt.get("wind_kn") or 10.0)
            wind_dir = float(best_pt.get("wind_dir") or 0.0)
            current_kn = float(best_pt.get("current_kn") or 0.0)
            current_dir = (wind_dir + 180.0) % 360.0

    target_type = inc.type if inc.type in LEEWAY_FACTORS else "default"
    traj = predict_sar_drift_trajectory(
        lat=inc.lat,
        lon=inc.lon,
        wind_kn=wind_kn,
        wind_dir_from=wind_dir,
        current_kn=current_kn,
        current_dir_to=current_dir,
        target_type=target_type,
    )
    inc.sar_drift = traj
