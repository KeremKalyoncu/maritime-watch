"""Astronomical solar calculations (Sunrise, Sunset, and Daylight Safety Cutoff).

Zero external dependencies: Pure mathematical implementation based on the standard
NOAA solar geometry algorithms. Accurately determines sunset/sunrise times within +-3 minutes
for Turkish coastal waters and ports.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SunCycle:
    sunrise_time: str  # "06:42" (HH:MM local)
    sunset_time: str  # "18:14" (HH:MM local)
    safe_return_cutoff: str  # Gün batımından 45 dk öncesi: "17:29" (HH:MM local)
    daylight_hours: float  # Toplam gün ışığı saati (örn: 11.53)
    sunrise_minutes: int  # Günün dakikası (0-1440)
    sunset_minutes: int  # Günün dakikası (0-1440)
    cutoff_minutes: int  # Günün dakikası (0-1440)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sunrise_time": self.sunrise_time,
            "sunset_time": self.sunset_time,
            "safe_return_cutoff": self.safe_return_cutoff,
            "daylight_hours": round(self.daylight_hours, 2),
        }


def _min_to_hhmm(minutes: int | float) -> str:
    """Format minutes from midnight into 'HH:MM' string, wrapping within 00:00-24:00."""
    total = int(round(minutes)) % 1440
    h = total // 60
    m = total % 60
    return f"{h:02d}:{m:02d}"


def calculate_sun_times(
    lat: float,
    lon: float,
    date: datetime.date | str | None = None,
    tz_offset_hours: float = 3.0,
    safe_margin_minutes: int = 45,
) -> SunCycle:
    """Calculate sunrise, sunset and daylight cutoff for a given coordinate and date.

    Uses standard NOAA solar position equations.
    Standard zenith for official sunrise/sunset is 90.833° (accounting for atmospheric refraction).
    Safe return cutoff is calculated as `sunset - safe_margin_minutes` (default 45 min).
    """
    # Parse date
    if date is None:
        target_date = datetime.datetime.now(datetime.timezone.utc).date()
    elif isinstance(date, str):
        target_date = datetime.date.fromisoformat(date.split("T")[0])
    else:
        target_date = date

    # Clamp coordinates to valid range
    lat = max(-89.0, min(89.0, float(lat)))
    lon = max(-180.0, min(180.0, float(lon)))

    # Day of year (1-366)
    day_of_year = target_date.timetuple().tm_yday

    # Fractional year in radians
    gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1)

    # Equation of time in minutes
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )

    # Solar declination angle in radians
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.001480 * math.sin(3.0 * gamma)
    )

    # Hour angle calculation for zenith 90.833 degrees
    zenith_rad = math.radians(90.833)
    lat_rad = math.radians(lat)

    cos_omega = (math.cos(zenith_rad) - math.sin(lat_rad) * math.sin(decl)) / (
        math.cos(lat_rad) * math.cos(decl)
    )

    # Polar day/night clamp
    if cos_omega >= 1.0:
        # Sun never rises
        return SunCycle(
            sunrise_time="00:00",
            sunset_time="00:00",
            safe_return_cutoff="00:00",
            daylight_hours=0.0,
            sunrise_minutes=0,
            sunset_minutes=0,
            cutoff_minutes=0,
        )
    elif cos_omega <= -1.0:
        # Sun never sets
        return SunCycle(
            sunrise_time="00:00",
            sunset_time="24:00",
            safe_return_cutoff="23:15",
            daylight_hours=24.0,
            sunrise_minutes=0,
            sunset_minutes=1440,
            cutoff_minutes=1440 - safe_margin_minutes,
        )

    omega_deg = math.degrees(math.acos(cos_omega))

    # UTC minutes from midnight
    sunrise_utc = 720.0 - 4.0 * lon - eqtime - 4.0 * omega_deg
    sunset_utc = 720.0 - 4.0 * lon - eqtime + 4.0 * omega_deg

    # Local time in minutes
    sunrise_local = (sunrise_utc + tz_offset_hours * 60.0) % 1440.0
    sunset_local = (sunset_utc + tz_offset_hours * 60.0) % 1440.0

    daylight_min = (sunset_local - sunrise_local) % 1440.0
    cutoff_local = max(0.0, sunset_local - safe_margin_minutes)

    return SunCycle(
        sunrise_time=_min_to_hhmm(sunrise_local),
        sunset_time=_min_to_hhmm(sunset_local),
        safe_return_cutoff=_min_to_hhmm(cutoff_local),
        daylight_hours=daylight_min / 60.0,
        sunrise_minutes=int(round(sunrise_local)),
        sunset_minutes=int(round(sunset_local)),
        cutoff_minutes=int(round(cutoff_local)),
    )
