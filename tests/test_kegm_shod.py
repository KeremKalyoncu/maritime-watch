import pytest
import requests

from src.ingest import _net
from src.ingest.kegm import scrape_kegm
from src.ingest.shod import _COORD_RE, _parse_coord_pair, scrape_shod


@pytest.fixture(autouse=True)
def _enable_samples(monkeypatch):
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", True)


def test_tc_scr_01_kegm_sample_parsing(monkeypatch):
    # Simulate offline by having requests.get fail
    def fail_get(*_args, **_kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(_net.requests, "get", fail_get)

    incs = scrape_kegm({})
    assert len(incs) >= 2

    # Verify extracted properties
    titles = " || ".join(s.detail for i in incs for s in i.sources)
    assert "Şile" in titles or "sile" in titles.lower()
    assert "Çanakkale" in titles or "canakkale" in titles.lower()

    # Verify source metadata
    for inc in incs:
        assert any(s.org == "Kıyı Emniyeti Genel Müdürlüğü" for s in inc.sources)
        assert inc.id.startswith("kegm-")


def test_tc_scr_01_shod_navtex_sample_parsing(monkeypatch):
    def fail_get(*_args, **_kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(_net.requests, "get", fail_get)

    warns = scrape_shod({})
    assert len(warns) >= 2

    headlines = " || ".join(w.headline for w in warns)
    assert "0842" in headlines
    assert "0845" in headlines

    istanbul_warn = next(w for w in warns if "0842" in w.headline)
    assert istanbul_warn.kind == "navtex"
    assert istanbul_warn.lat is not None
    assert istanbul_warn.lon is not None
    assert 40.0 <= istanbul_warn.lat <= 41.5
    assert 28.0 <= istanbul_warn.lon <= 30.0


def test_tc_scr_02_server_error_fallback(monkeypatch):
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", False)

    def fail_get(*_args, **_kwargs):
        raise requests.HTTPError("504 Gateway Timeout")

    monkeypatch.setattr(_net.requests, "get", fail_get)

    # When SAMPLES_ALLOWED is False, errors should gracefully return empty lists
    assert scrape_kegm({}) == []
    assert scrape_shod({}) == []


def test_tc_scr_03_coord_parsing():
    sample_text = "40 50.20 K - 028 45.10 D"
    m = _COORD_RE.search(sample_text)
    assert m is not None
    lat, lon = _parse_coord_pair(m)
    assert abs(lat - (40.0 + 50.20 / 60.0)) < 0.001
    assert abs(lon - (28.0 + 45.10 / 60.0)) < 0.001
