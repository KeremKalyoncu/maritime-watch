"""The fixtures in src/ingest/samples/ must never reach published output.

This is a real production incident, not a hypothetical: a dead Open-Meteo fetch
put the fixture's "dalga ~2.7 m, ruzgar hamlesi ~41 kn" on the live Telegram
channel as a genuine forecast for two different sea areas. Every source had the
same hole — all eleven ingest modules discarded the `live` flag.
"""

import pytest
import requests

from src.ingest import (
    _net,
    eonet,
    gdacs,
    metar,
    navwarn,
    news,
    official,
    openmeteo,
    quakes,
    reliefweb,
)

ALL_SOURCES = [
    ("openmeteo", lambda cfg: openmeteo.fetch_marine_warnings(cfg)),
    ("quakes", lambda cfg: quakes.fetch_quakes(cfg)),
    ("gdacs", lambda cfg: gdacs.fetch_gdacs(cfg)),
    ("eonet", lambda cfg: eonet.fetch_eonet(cfg)),
    ("metar", lambda cfg: metar.fetch_metar(cfg)),
    ("navwarn", lambda cfg: navwarn.fetch_navwarnings(cfg)),
    ("reliefweb", lambda cfg: reliefweb.fetch_reliefweb(cfg)),
    ("news", lambda cfg: news.fetch_news(cfg)),
    ("sahil_guvenlik", lambda cfg: official.scrape_sahil_guvenlik(cfg)),
    ("afad", lambda cfg: official.scrape_afad(cfg)),
    ("mgm", lambda cfg: official.scrape_mgm_marine(cfg)),
]


@pytest.fixture
def dead_network(monkeypatch):
    def boom(*_a, **_k):
        raise requests.RequestException("every source is down")
    monkeypatch.setattr(_net.requests, "get", boom)
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", False)   # production setting
    _net.reset_status()


@pytest.mark.parametrize("name,fetch", ALL_SOURCES, ids=[n for n, _ in ALL_SOURCES])
def test_dead_source_publishes_nothing(name, fetch, cfg, dead_network):
    assert fetch(cfg) == [], f"{name} fabricated records from its fixture"


def test_fetch_status_marks_dead_sources(cfg, dead_network):
    openmeteo.fetch_marine_warnings(cfg)
    assert _net.STATUS, "no fetch was recorded"
    assert set(_net.STATUS.values()) == {"down"}
    assert "live" not in _net.STATUS.values()


def test_samples_still_usable_when_explicitly_enabled(cfg, monkeypatch):
    """Tests and offline demos may still parse fixtures - the switch is opt-in."""
    def boom(*_a, **_k):
        raise requests.RequestException("offline")
    monkeypatch.setattr(_net.requests, "get", boom)
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", True)
    _net.reset_status()
    raw, live = _net.get_text("https://example.invalid", "openmeteo_marine.json")
    assert raw and live is False
    assert _net.STATUS["openmeteo_marine.json"] == "sample"


def test_missing_sample_never_crashes(monkeypatch):
    def boom(*_a, **_k):
        raise requests.RequestException("offline")
    monkeypatch.setattr(_net.requests, "get", boom)
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", True)
    _net.reset_status()
    raw, live = _net.get_text("https://example.invalid", "does_not_exist.json")
    assert raw == "" and live is False
    assert _net.STATUS["does_not_exist.json"] == "down"
