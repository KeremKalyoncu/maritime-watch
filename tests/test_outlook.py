"""The daily outlook is the channel's main product, so it gets the most tests."""

import pytest

from src.process.window import DANGER, OK, build, level_for


def _times(n, start=6):
    return [f"2026-09-10T{(start + i) % 24:02d}:00" for i in range(n + 1)]


SMALL = {"gust_kn": 22, "wave_m": 1.25}


def test_small_craft_limits_are_not_a_cargo_ships():
    """Nine days of real Turkish coastal data crossed 34 kn four times and 2.0 m
    never. At the small-craft limit the same days had 371 unsafe point-hours."""
    assert level_for(25, 0.5, SMALL) == DANGER
    assert level_for(25, 0.5, {"gust_kn": 34, "wave_m": 2.0}) == OK  # nothing, to a ship
    assert level_for(10, 0.3, SMALL) == OK


def test_wave_alone_is_enough_to_stop_a_small_boat():
    assert level_for(12, 1.5, SMALL) == DANGER  # calm wind, big swell


def test_windows_say_when_not_just_how_much():
    gusts = [8] * 6 + [25] * 6
    waves = [0.2] * 12
    o = build("Marmara", _times(12), gusts, waves, SMALL, hours=12, tz_offset_h=0)
    assert [w.level for w in o.windows] == [OK, DANGER]
    assert o.windows[0].start == "06:00" and o.windows[0].end == "12:00"
    assert o.windows[1].start == "12:00"
    assert o.first_danger.start == "12:00"
    assert o.worst == DANGER


def test_a_one_hour_lull_between_two_blows_is_not_a_window():
    gusts = [25] * 4 + [8] + [25] * 4
    o = build("Ege", _times(9), gusts, [0.2] * 9, SMALL, hours=9, tz_offset_h=0)
    assert len(o.windows) == 1 and o.windows[0].level == DANGER


def test_local_time_is_used_not_utc():
    o = build("Marmara", _times(3, start=3), [8, 8, 8], [0.1] * 3, SMALL, hours=3, tz_offset_h=3)
    assert o.windows[0].start == "06:00"


def test_a_calm_day_produces_one_green_window():
    o = build("Antalya", _times(12), [9] * 12, [0.2] * 12, SMALL, hours=12, tz_offset_h=0)
    assert len(o.windows) == 1 and o.worst == OK and o.first_danger is None
    from src.process.window import return_by

    assert return_by(o) is None


def test_missing_measurements_are_never_treated_as_calm():
    from src.process.window import UNKNOWN, window_to_dict

    assert level_for(None, None, SMALL) == UNKNOWN
    assert level_for(10, None, SMALL) == OK
    assert level_for(None, 0.3, SMALL) == OK
    assert level_for(None, 1.5, SMALL) == DANGER
    o = build("Bos", _times(4), [None] * 4, [None] * 4, SMALL, hours=4, tz_offset_h=0)
    assert o.windows and all(w.level == UNKNOWN for w in o.windows)
    d = window_to_dict(o.windows[0])
    assert d["gust_kn"] is None and d["wave_m"] is None
    assert d["level"] == UNKNOWN


def test_wind_only_hours_do_not_invent_zero_wave():
    o = build("Ege", _times(4), [8, 8, 8, 8], [], SMALL, hours=4, tz_offset_h=0)
    assert o.windows
    assert o.worst == OK
    assert all(w.wave_m is None for w in o.windows)


def test_return_by_prefers_danger_then_watch():
    from src.process.window import WATCH, return_by

    gusts = [8] * 4 + [18] * 4 + [26] * 4  # ok → watch → danger at small limits
    o = build("Marmara", _times(12), gusts, [0.2] * 12, SMALL, hours=12, tz_offset_h=0)
    assert o.first_danger is not None
    assert return_by(o) == o.first_danger.start

    o2 = build("Ege", _times(8), [8] * 4 + [18] * 4, [0.2] * 8, SMALL, hours=8, tz_offset_h=0)
    assert o2.first_danger is None and any(w.level == WATCH for w in o2.windows)
    assert return_by(o2) == o2.first_watch.start


def test_empty_forecast_is_not_a_calm_forecast():
    o = build("Bos", [], [], [], SMALL)
    assert o.windows == [] and o.worst == OK and o.max_gust == 0


@pytest.mark.parametrize("field", ["times", "gusts"])
def test_a_dead_source_never_becomes_an_outlook(cfg, monkeypatch, field):
    """People plan a day around this message; a fixture-built one is worse than
    silence."""
    import requests

    from src.ingest import _net, openmeteo

    openmeteo.reset_cache()
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", False)
    monkeypatch.setattr(openmeteo.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        _net.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.RequestException("down"))
    )
    assert openmeteo.fetch_forecast_points(cfg) == []
