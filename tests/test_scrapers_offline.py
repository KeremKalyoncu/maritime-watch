"""Scrapers must degrade to cached samples when the network is unavailable."""

import pytest
import requests

from src.ingest import _net, official
from src.ingest.official import _collapse_dup, _norm


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*_a, **_k):
        raise requests.RequestException("no network in tests")
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", True)
    monkeypatch.setattr(_net.requests, "get", boom)


def test_mgm_parses_sample(cfg):
    warns = official.scrape_mgm_marine(cfg)
    assert warns, "expected at least one warning from the cached MGM sample"
    areas = {w.area for w in warns}
    assert "Marmara Denizi" in areas
    marmara = next(w for w in warns if w.area == "Marmara Denizi")
    assert marmara.severity == "major"
    assert marmara.lat is not None and marmara.lon is not None


@pytest.fixture
def all_scrapers(cfg):
    """config.yaml keeps mgm/afad off because their endpoints 404, but the parsers
    are still shipped, so they still need coverage."""
    cfg["scrape"] = {**cfg["scrape"], "mgm": True, "afad": True}
    return cfg


def test_sg_and_afad_parse_samples(all_scrapers):
    cfg = all_scrapers
    incs, warns = official.gather_official(cfg)
    assert len(incs) >= 3
    assert len(warns) >= 1

    titles = " || ".join(s.detail for i in incs for s in i.sources)
    assert "Mudanya" in titles
    assert "Zonguldak" in titles

    mudanya = next(i for i in incs if any("Mudanya" in s.detail for s in i.sources))
    assert mudanya.casualties == 4
    assert mudanya.lat is not None            # geocoded from the place name
    assert all(s.kind == "official" for i in incs for s in i.sources)


def test_non_keyword_headlines_are_skipped(cfg):
    incs = official.scrape_sahil_guvenlik(cfg)
    joined = " ".join(s.detail for i in incs for s in i.sources)
    assert "Personel atama" not in joined
    assert "eğitim faaliyeti" not in joined


def test_collapse_dup():
    assert _collapse_dup("Tekne battı Tekne battı") == "Tekne battı"
    assert _collapse_dup("02.09 İzmir 20 göçmen İzmir 20 göçmen") == "02.09 İzmir 20 göçmen"
    assert _collapse_dup("Mudanya açıklarında tekne kurtarıldı") == "Mudanya açıklarında tekne kurtarıldı"


def test_norm_turkish_i():
    assert "izmir" in _norm("İZMİR Açıkları")


def test_scraped_ids_are_stable_across_calls(all_scrapers):
    cfg = all_scrapers
    a = {i.id for i in official.gather_official(cfg)[0]}
    b = {i.id for i in official.gather_official(cfg)[0]}
    assert a == b and len(a) >= 3


def test_mgm_alarms_keep_marine_and_drop_inland(cfg):
    ws = official.scrape_mgm_alarms(cfg)
    heads = " | ".join(w.headline for w in ws)
    assert "Marmara" in heads                       # storm warning kept
    assert "Antalya" in heads                       # coastal, geocoded by province
    assert "Konya" not in heads and "Erzurum" not in heads      # inland dropped
    assert all(w.org == "Meteoroloji Genel Müdürlüğü" for w in ws)
    assert all(w.url.startswith("https://www.mgm.gov.tr/") for w in ws)
    rapor = next(w for w in ws if "RAPOR" in w.headline)
    assert rapor.severity == "minor" and rapor.url.endswith("e")


def test_mgm_alarms_survive_a_changed_schema(cfg, monkeypatch):
    """Undocumented endpoint: a shape change must yield nothing, never a crash."""
    for body in ("{}", "[]", '[{"x": 1}]', '["not a dict"]', "not json at all", ""):
        monkeypatch.setattr(official, "_fetch", lambda *a, **k: (body, True))
        assert official.scrape_mgm_alarms(cfg) == []


def test_ids_do_not_carry_todays_date(cfg, monkeypatch):
    """An announcement stays on the Coast Guard page for days. When the id
    embedded the fetch date, one rescue landed as three incidents on the map."""
    import time as _t
    seen = []
    for day in ("2026-09-03", "2026-09-04", "2026-09-05"):
        monkeypatch.setattr(_t, "strftime", lambda f, *a, d=day: d + "T09:00:00Z")
        seen.append({i.id for i in official.scrape_sahil_guvenlik(cfg)})
    assert seen[0] == seen[1] == seen[2]
    assert all(not i.startswith("2026-") for i in seen[0])
