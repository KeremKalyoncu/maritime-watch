"""outlook.json presenter — go/no-go cache for web + bot."""

from src.render.outlook import render_outlook


def _pts():
    # start=6 so with tz=0 danger half begins at 12:00 local (matches other outlook tests)
    times = [f"2026-09-10T{(6 + i) % 24:02d}:00" for i in range(13)]
    return [
        {
            "name": "Marmara Denizi",
            "lat": 40.7,
            "lon": 28.2,
            "times": times,
            "gusts": [8] * 6 + [26] * 6,
            "waves": [0.3] * 12,
        },
        {
            "name": "Kuzey Ege",
            "lat": 39.5,
            "lon": 26.0,
            "times": times,
            "gusts": [10] * 12,
            "waves": [0.4] * 12,
        },
    ]


def test_render_outlook_writes_three_classes(cfg, tmp_path):
    cfg = dict(cfg)
    cfg["outlook"] = dict(cfg.get("outlook") or {})
    cfg["outlook"]["tz_offset_hours"] = 0
    out = tmp_path / "outlook.json"
    payload = render_outlook(cfg, out, points=_pts())
    assert payload is not None
    assert payload["schema_version"] == 1
    assert payload["question"] == "today"
    assert set(payload["classes"]) == {"small", "medium", "large"}
    small = payload["classes"]["small"]
    assert small["areas"]
    area = next(a for a in small["areas"] if a["name"] == "Marmara Denizi")
    assert area["return_by"] == "12:00"
    assert area["worst"] == "danger"
    assert out.is_file()
    assert out.stat().st_size < 256_000


def test_render_outlook_skips_when_no_points(cfg, tmp_path):
    out = tmp_path / "outlook.json"
    assert render_outlook(cfg, out, points=[]) is None
    assert not out.exists()


def test_render_outlook_large_class_calmer_than_small(cfg, tmp_path):
    cfg = dict(cfg)
    cfg["outlook"] = dict(cfg.get("outlook") or {})
    cfg["outlook"]["tz_offset_hours"] = 0
    payload = render_outlook(cfg, tmp_path / "o.json", points=_pts())
    marmara_small = next(a for a in payload["classes"]["small"]["areas"] if a["name"] == "Marmara Denizi")
    marmara_large = next(a for a in payload["classes"]["large"]["areas"] if a["name"] == "Marmara Denizi")
    assert marmara_small["worst"] == "danger"
    assert marmara_large["worst"] in ("ok", "watch")


def test_render_outlook_reports_coverage_missing(cfg, tmp_path):
    cfg = dict(cfg)
    cfg["outlook"] = dict(cfg.get("outlook") or {})
    payload = render_outlook(cfg, tmp_path / "c.json", points=_pts())
    cov = payload["coverage"]
    assert cov["present"] == 2
    assert cov["expected"] >= 2
    assert "Marmara Denizi" not in cov["missing"]
    assert cov["missing"] or cov["expected"] == cov["present"]
