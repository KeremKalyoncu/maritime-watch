"""Unit tests for the publish-artifact CI gate."""

import json
from pathlib import Path

import pytest

from scripts import ci_validate_publish as v


@pytest.fixture
def web_data(tmp_path, monkeypatch):
    d = tmp_path / "web" / "data"
    d.mkdir(parents=True)
    monkeypatch.setattr(v, "WEB_DATA", d)
    monkeypatch.setattr(v, "ROOT", tmp_path)
    return d


def _write(d: Path, name: str, obj):
    d.joinpath(name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_outlook_ok_with_coverage(web_data):
    _write(
        web_data,
        "outlook.json",
        {
            "schema_version": 1,
            "generated": "2026-09-19T12:00:00Z",
            "coverage": {"expected": 2, "present": 1, "missing": ["X"]},
            "classes": {
                "small": {
                    "areas": [
                        {
                            "name": "A",
                            "windows": [
                                {"start": "06:00", "end": "12:00", "level": "ok", "gust_kn": 8, "wave_m": 0.3}
                            ],
                        }
                    ]
                },
                "medium": {"areas": []},
                "large": {"areas": []},
            },
        },
    )
    notes = v.validate_outlook(v._load("outlook.json"))
    assert any("coverage" in n for n in notes)


def test_outlook_rejects_bad_level(web_data):
    _write(
        web_data,
        "outlook.json",
        {
            "schema_version": 1,
            "generated": "2026-09-19T12:00:00Z",
            "classes": {
                "small": {"areas": [{"name": "A", "windows": [{"level": "green"}]}]},
                "medium": {"areas": []},
                "large": {"areas": []},
            },
        },
    )
    with pytest.raises(SystemExit, match="window level"):
        v.validate_outlook(v._load("outlook.json"))


def test_outlook_rejects_fixture_fingerprint(web_data):
    _write(
        web_data,
        "outlook.json",
        {
            "schema_version": 1,
            "generated": "2026-09-19T12:00:00Z",
            "classes": {
                "small": {"areas": [{"name": "A", "note": "dalga ~2.7 m"}]},
                "medium": {"areas": []},
                "large": {"areas": []},
            },
        },
    )
    with pytest.raises(SystemExit, match="fixture"):
        v.validate_outlook(v._load("outlook.json"))


def test_safety_rejects_unknown_perfect_score(web_data):
    _write(
        web_data,
        "safety_index.json",
        {
            "ratings": [{"area": "X", "score": 100, "data_quality": "unknown"}],
        },
    )
    with pytest.raises(SystemExit, match="unknown quality"):
        v.validate_safety(v._load("safety_index.json"))


def test_health_rejects_sample_status(web_data):
    _write(
        web_data,
        "health.json",
        {
            "fetch": {"openmeteo_wind.json": "sample"},
        },
    )
    with pytest.raises(SystemExit, match="sample-backed"):
        v.validate_health(v._load("health.json"))


def test_missing_outlook_is_soft(web_data):
    notes = v.validate_outlook(None)
    assert any("missing" in n for n in notes)
