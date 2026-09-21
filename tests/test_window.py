from __future__ import annotations

from src.process.window import (
    DANGER,
    OK,
    WATCH,
    area_to_public_dict,
    build,
    level_for,
    return_by,
)

SMALL = {"gust_kn": 22, "wave_m": 1.25}


def test_level_for_fog_hard_gate():
    # Visibility < 300m -> DANGER, even with zero wind and zero wave
    assert level_for(2.0, 0.1, SMALL, visibility=250) == DANGER
    assert level_for(0.0, 0.0, SMALL, visibility=100) == DANGER

    # Visibility 300m - 1000m -> WATCH (mist/fog warning)
    assert level_for(5.0, 0.2, SMALL, visibility=800) == WATCH

    # Visibility >= 1000m -> OK (normal conditions apply)
    assert level_for(5.0, 0.2, SMALL, visibility=5000) == OK


def test_level_for_wave_steepness_penalty():
    # 0.8m wave with 8.0s period -> under 0.75 * 1.25 (0.937m), so OK
    assert level_for(10.0, 0.8, SMALL, period=8.0) == OK

    # 1.0m wave with 8.0s period -> 1.0 >= 0.937m, so WATCH
    assert level_for(10.0, 1.0, SMALL, period=8.0) == WATCH

    # 1.0m wave with 3.2s period -> short choppy breaking wave, threshold tightened by 30%
    # w_lim drops from 1.25 to 0.875m. Since 1.0m >= 0.875m, this becomes DANGER!
    assert level_for(10.0, 1.0, SMALL, period=3.2) == DANGER


def test_build_sunset_ceiling_clamp():
    # Istanbul: Lat 41.0, Lon 29.0 on 2026-03-21 (Sunset ~19:15-19:25 local, Safe cutoff ~18:30)
    # Start at 03:00 UTC (06:00 local time UTC+3)
    times = [f"2026-03-21T{h:02d}:00" for h in range(3, 21)]
    # Wind becomes dangerous at 17:00 UTC (20:00 local time UTC+3)
    gusts = [10.0] * 14 + [25.0] * 4
    waves = [0.3] * 18

    area = build(
        "Marmara Denizi",
        times,
        gusts,
        waves,
        SMALL,
        hours=18,
        tz_offset_h=3.0,
        lat=41.0,
        lon=29.0,
        date="2026-03-21",
    )
    assert area.sunset_time != ""
    assert area.safe_cutoff != ""

    # Danger window starts at 20:00 local time, but return_by must be clamped by sunset cutoff (~18:31)
    rb = return_by(area)
    assert rb is not None
    assert rb == area.safe_cutoff
    assert int(rb.split(":")[0]) <= 19


def test_build_with_marine_physics_metadata():
    times = ["2026-09-21T06:00", "2026-09-21T07:00", "2026-09-21T08:00"]
    gusts = [15.0, 18.0, 12.0]
    waves = [1.1, 1.2, 0.9]
    periods = [3.4, 3.2, 3.5]  # Steep waves
    wind_dirs = [225.0, 220.0, 230.0]  # Lodos
    visibilities = [800.0, 750.0, 1200.0]  # Fog / mist

    area = build(
        "Marmara",
        times,
        gusts,
        waves,
        SMALL,
        hours=3,
        lat=40.75,
        lon=28.3,
        wave_periods=periods,
        wind_dirs=wind_dirs,
        visibilities=visibilities,
    )

    assert area.cur_wind_name == "Lodos"
    assert area.cur_wave_period == 3.4
    assert area.steepness_hazard is True
    assert area.fog_hazard is True

    pub = area_to_public_dict(area)
    assert pub["cur_wind_name"] == "Lodos"
    assert pub["steepness_hazard"] is True
    assert pub["fog_hazard"] is True
    assert len(pub["windows"]) > 0
    assert pub["windows"][0]["dominant_wind"] == "Lodos"
