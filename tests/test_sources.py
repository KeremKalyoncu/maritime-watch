"""Every extra source must parse its cached sample when offline."""

import pytest
import requests

from src.ingest import _net, eonet, gdacs, metar, navwarn, news, openmeteo, quakes, reliefweb


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    def boom(*_a, **_k):
        raise requests.RequestException("offline in tests")
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", True)
    monkeypatch.setattr(_net.requests, "get", boom)


def test_openmeteo_parses_the_fixture_but_publishes_nothing_from_it(cfg):
    # the parser must work on the fixture...
    waves, live = openmeteo._series(
        openmeteo.MARINE, {"latitude": 40.75, "longitude": 28.3},
        "openmeteo_marine.json", "wave_height")
    assert waves and max(waves) == 2.7 and live is False
    # ...but a forecast built from fixture numbers must never be published.
    # This exact leak put "dalga 2.7 m / 41 kn" on the live channel as real.
    assert openmeteo.fetch_marine_warnings(cfg) == []


def test_quakes_multi_provider_and_coastal(cfg):
    ws = quakes.fetch_quakes(cfg)
    orgs = {w.org for w in ws}
    assert {"AFAD", "USGS", "EMSC"} <= orgs        # all three providers parsed
    locs = " | ".join(w.headline for w in ws)
    assert "Marmara" in locs
    assert "Elazığ" not in locs                    # inland AFAD quake dropped
    assert "Honshu" not in locs                    # out-of-region USGS quake dropped
    assert all(w.kind == "earthquake" for w in ws)


def test_quakes_same_event_merges_in_store(cfg, tmp_path):
    from src.store import Store
    s = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))
    for w in quakes.fetch_quakes(cfg):
        s.upsert_warning(w)
    # AFAD+USGS+EMSC all report the Marmara M~4.2 quake -> one stored warning for it
    marmara = [w for w in s.warnings.values() if "Marmara" in w.area or "MARMARA" in w.area.upper()]
    assert len(marmara) == 1
    assert len(marmara[0].orgs) >= 2


def test_eonet_sample_region_filter(cfg):
    ws = eonet.fetch_eonet(cfg)
    assert len(ws) == 1                    # Black Sea storm kept, Canada wildfire dropped
    assert ws[0].kind == "eonet"


def test_reliefweb_sample(cfg):
    ws = reliefweb.fetch_reliefweb(cfg)
    assert ws and ws[0].org == "ReliefWeb"
    assert "Türkiye" in ws[0].headline or "Turkey" in ws[0].headline


def test_navwarn_sample_filters_region(cfg):
    ws = navwarn.fetch_navwarnings(cfg)
    text = " | ".join(w.headline for w in ws)
    assert "AEGEAN" in text.upper() or "BLACK SEA" in text.upper()
    assert "BARCELONA" not in text.upper()
    assert all(w.kind == "nav-warning" for w in ws)


def test_news_sample_keyword_filter(cfg):
    incs = news.fetch_news(cfg)
    titles = " | ".join(s.detail for i in incs for s in i.sources)
    assert "alabora" in titles
    assert "battı" in titles
    assert "faiz" not in titles.lower()
    assert all(s.kind == "news" for i in incs for s in i.sources)


def test_gdacs_sample_region_and_level(cfg):
    ws = gdacs.fetch_gdacs(cfg)
    assert len(ws) == 1                    # Turkey/Orange kept, France/Green dropped
    assert ws[0].kind == "gdacs"
    assert ws[0].lat is not None


def test_metar_sample(cfg):
    ws = metar.fetch_metar(cfg)
    names = " | ".join(w.headline for w in ws)
    assert "Ataturk" in names              # gust 38 kn
    assert "Bodrum" in names               # thunderstorm / low vis
    assert "Antalya" not in names          # calm
