from __future__ import annotations

import datetime

from src.process.astronomy import calculate_sun_times


def test_calculate_sun_times_istanbul_equinox():
    # Istanbul: Lat ~41.0, Lon ~29.0 on March 21 (Equinox)
    # Sunrise ~07:05-07:15 UTC+3, Sunset ~19:15-19:25 UTC+3
    res = calculate_sun_times(41.0, 29.0, date="2026-03-21", tz_offset_hours=3.0)
    assert 6 <= int(res.sunrise_time.split(":")[0]) <= 7
    assert 19 <= int(res.sunset_time.split(":")[0]) <= 20
    assert 11.5 <= res.daylight_hours <= 12.5

    # Safe return cutoff must be exactly 45 minutes before sunset
    cutoff_h, cutoff_m = map(int, res.safe_return_cutoff.split(":"))
    sunset_h, sunset_m = map(int, res.sunset_time.split(":"))
    cutoff_total = cutoff_h * 60 + cutoff_m
    sunset_total = sunset_h * 60 + sunset_m
    assert sunset_total - cutoff_total == 45


def test_calculate_sun_times_summer_vs_winter():
    # Antalya: Lat 36.9, Lon 30.7
    # Summer (June 21): Long daylight (> 14h)
    summer = calculate_sun_times(36.9, 30.7, date="2026-06-21", tz_offset_hours=3.0)
    # Winter (Dec 21): Short daylight (< 10h)
    winter = calculate_sun_times(36.9, 30.7, date="2026-12-21", tz_offset_hours=3.0)

    assert summer.daylight_hours > 14.0
    assert winter.daylight_hours < 10.0
    assert summer.sunset_minutes > winter.sunset_minutes


def test_calculate_sun_times_date_formats():
    # Test date object vs string vs None
    d = datetime.date(2026, 9, 21)
    res1 = calculate_sun_times(41.0, 29.0, date=d)
    res2 = calculate_sun_times(41.0, 29.0, date="2026-09-21")
    assert res1.sunset_time == res2.sunset_time
    assert res1.safe_return_cutoff == res2.safe_return_cutoff


def test_calculate_sun_times_boundary_clamp():
    # Polar clamp safety
    polar_north = calculate_sun_times(89.0, 29.0, date="2026-06-21")
    assert polar_north.daylight_hours in (0.0, 24.0)
