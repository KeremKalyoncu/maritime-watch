"""data/health_history.jsonl: one line per cycle for the weekly source-health report."""

import json

from src import health_history as hh
from src.render.health import write_health

CFG = {"openmeteo": {"points": [{"name": "Marmara Denizi"}, {"name": "Batı Karadeniz"}, {"name": "Kuzey Ege"}]}}


def test_forecast_missing_names_the_areas_without_a_forecast():
    got = [{"name": "Marmara Denizi"}, {"name": "Kuzey Ege"}]
    assert hh.forecast_missing(CFG, got) == ["Batı Karadeniz"]
    assert hh.forecast_missing(CFG, None) == ["Marmara Denizi", "Batı Karadeniz", "Kuzey Ege"]  # fetch failed
    assert hh.forecast_missing({}, got) == []


def test_entry_keeps_only_what_went_wrong():
    e = hh.entry(
        started=0,
        seconds=107.94,
        fetch_status={"news_0.xml": "live", "shod_navtex.txt": "down", "openmeteo_wind:Batı Karadeniz": "down"},
        sources_down=[],
        om_missing=["Batı Karadeniz"],
        ais_positions=141,
        vessels=725,
    )
    assert e == {
        "t": "1970-01-01T00:00:00Z",
        "s": 107.9,
        "ais": 141,
        "vessels": 725,
        "down": ["openmeteo_wind:Batı Karadeniz", "shod_navtex.txt"],
        "om_miss": ["Batı Karadeniz"],
    }
    calm = hh.entry(started=0, seconds=1, fetch_status={"a": "live"}, sources_down=[], om_missing=[],
                    ais_positions=None, vessels=None, power=None)
    assert set(calm) == {"t", "s", "ais", "vessels"}  # AIS off stays None, not 0


def test_append_writes_one_line_per_cycle_and_trims(tmp_path):
    p = tmp_path / "data" / "health_history.jsonl"
    for i in range(23):
        hh.append(p, {"t": str(i)}, keep=10)
    lines = p.read_text("utf-8").splitlines()
    # trimmed back to 10 once it passed 11, then grew again
    assert 10 <= len(lines) <= 11
    assert json.loads(lines[-1]) == {"t": "22"}
    assert not (tmp_path / "data" / "health_history.jsonl.tmp").exists()


def test_health_json_lists_missing_forecast_areas(tmp_path):
    h = write_health(str(tmp_path), [{"source": "openmeteo", "ok": True, "items": 12, "error": None}],
                     0.0, 0, 0, fetch_status={}, forecast_missing=["Batı Karadeniz"])
    assert h["forecast_missing"] == ["Batı Karadeniz"]
    assert json.loads((tmp_path / "health.json").read_text("utf-8"))["forecast_missing"] == ["Batı Karadeniz"]
