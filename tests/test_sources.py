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


def test_openmeteo_continues_when_one_point_fails(cfg, monkeypatch):
    calls = []
    def fake_series(url, params, sample, field):
        calls.append(params.get("latitude"))
        if len(calls) <= 2:
            return [1.0], False
        return [3.5], True  # wave >= om["wave_m"]
    monkeypatch.setattr(openmeteo, "_series", fake_series)
    ws = openmeteo.fetch_marine_warnings(cfg)
    assert len(calls) > 2
    assert len(ws) > 0


def test_quakes_multi_provider_and_coastal(cfg):
    ws = quakes.fetch_quakes(cfg)
    orgs = {w.org for w in ws}
    assert {"AFAD", "USGS", "EMSC", "Kandilli Rasathanesi"} <= orgs        # all providers parsed
    locs = " | ".join(w.headline for w in ws)
    assert "Marmara" in locs or "MARMARA" in locs
    assert "Elazığ" not in locs                    # inland AFAD quake dropped
    assert "Honshu" not in locs                    # out-of-region USGS quake dropped
    assert all(w.kind == "earthquake" for w in ws)


def test_kandilli_sample_coastal_filter(cfg):
    from src.ingest.kandilli import fetch_kandilli
    ws = fetch_kandilli(cfg)
    assert len(ws) == 1
    assert ws[0].org == "Kandilli Rasathanesi"
    assert "MARMARA" in ws[0].headline or "Marmara" in ws[0].headline
    assert ws[0].value == 4.2


def test_quakes_same_event_merges_in_store(cfg, tmp_path):
    from src.store import Store
    s = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))
    for w in quakes.fetch_quakes(cfg):
        s.upsert_warning(w)
    # AFAD+USGS+EMSC+Kandilli all report the Marmara M~4.2 quake -> one stored warning for it
    marmara = [w for w in s.warnings.values() if "Marmara" in w.area or "MARMARA" in w.area.upper()]
    assert len(marmara) == 1
    assert len(marmara[0].orgs) >= 3


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


def test_forecast_window_starts_at_the_current_hour(monkeypatch):
    """Open-Meteo answers from 00:00 UTC. Taking the first N hours meant a run at
    23:00 looked 13 hours ahead while the message promised 36."""
    import time as _t

    from src.ingest import openmeteo
    body = {"hourly": {"time": [f"2026-09-05T{h:02d}:00" for h in range(24)],
                       "wave_height": [float(h) for h in range(24)]}}
    monkeypatch.setattr(openmeteo, "get_json", lambda *a, **k: (body, True))
    monkeypatch.setattr(_t, "gmtime", lambda *a: _t.strptime("2026-09-05T20:00", "%Y-%m-%dT%H:%M"))
    vals, live = openmeteo._series("u", {}, "s", "wave_height")
    assert vals == [20.0, 21.0, 22.0, 23.0] and live


def test_forecast_falls_back_to_the_whole_series_when_times_are_missing(monkeypatch):
    from src.ingest import openmeteo
    monkeypatch.setattr(openmeteo, "get_json",
                        lambda *a, **k: ({"hourly": {"wave_height": [1.0, 2.0]}}, True))
    assert openmeteo._series("u", {}, "s", "wave_height")[0] == [1.0, 2.0]


def test_tc_met_01_and_02_metar_fog_detection(cfg, monkeypatch):
    # Test 1: Foggy station (vis 300m, FG)
    fog_data = [
        {"icaoId": "LTBA", "name": "Istanbul Ataturk", "wspd": 4, "wgst": 6, "visib": "0.2", "wxString": "FG", "lat": 40.97, "lon": 28.81},
        {"icaoId": "LTAI", "name": "Antalya", "wspd": 5, "wgst": 8, "visib": "10+", "wxString": "CAVOK", "lat": 36.89, "lon": 30.80},
    ]
    monkeypatch.setattr(metar, "get_json", lambda *a, **k: (fog_data, True))

    ws = metar.fetch_metar(cfg)
    assert len(ws) == 1
    fog_warn = ws[0]
    assert fog_warn.kind == "fog"
    assert fog_warn.severity == "major"
    assert "yoğun sis" in fog_warn.headline.lower()


def test_tc_met_03_and_04_incident_weather_correlation():
    from src.model import Incident
    from src.process.classify import enrich_weather_context

    weather_points = [
        {
            "name": "Bodrum",
            "lat": 37.03,
            "lon": 27.43,
            "wind_kn": 22.0,
            "gust_kn": 30.0,
            "wave_m": 1.6,
            "wind_dir": 225,  # SW = Lodos
            "beaufort": 6,
        },
        {
            "name": "İstanbul Boğazı",
            "lat": 41.10,
            "lon": 29.05,
            "wind_kn": 14.0,
            "gust_kn": 18.0,
            "wave_m": 0.6,
            "wind_dir": 45,   # NE = Poyraz
            "beaufort": 4,
        },
    ]

    # Close incident: ~2 NM from Bodrum
    inc_close = Incident(id="inc-close", lat=37.01, lon=27.41)
    enrich_weather_context(inc_close, weather_points, max_dist_nm=35.0)
    assert inc_close.weather_context is not None
    assert inc_close.weather_context.station_name == "Bodrum"
    assert inc_close.weather_context.wind_kn == 22.0
    assert inc_close.weather_context.wave_m == 1.6
    assert "Lodos" in inc_close.weather_context.summary_tr
    assert "1.6 m dalga" in inc_close.weather_context.summary_tr

    # Far incident: 80 NM away in open Mediterranean
    inc_far = Incident(id="inc-far", lat=35.50, lon=28.00)
    enrich_weather_context(inc_far, weather_points, max_dist_nm=35.0)
    assert inc_far.weather_context is None

