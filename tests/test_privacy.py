"""Named individuals must not reach the map, the channel or the git history."""

from src.ingest.news import _norm
from src.process.privacy import REDACTED, drop_aftermath, redact


def _after(cfg):
    return [_norm(w) for w in cfg["news"]["aftermath_words"]]


def test_victim_name_is_redacted():
    t = "KKTC'deki gemi kazasında hayatını kaybeden Elmas Demir'in cenazesi Eskişehir'e getirildi"
    out = redact(t)
    assert "Elmas Demir" not in out and REDACTED in out
    assert "Eskişehir'e getirildi" in out      # the rest of the headline survives


def test_relative_name_is_redacted():
    assert "Elmas Demir" not in redact("Elmas Demir'in acılı eşi: Mürettebat yolcuları terk etti")


def test_vessel_name_that_looks_like_a_person_survives():
    t = "Silivri açıklarında Tuğberk İmamoğlu'nun mürettebatı aranıyor"
    assert redact(t, keep=("Tuğberk İmamoğlu",)) == t


def test_places_and_institutions_are_not_names():
    for t in ("Marmara Denizi'nde fırtına, Ege Denizi'nde ulaşıma ara verildi",
              "Sahil Güvenlik Komutanlığı'nın ekipleri bölgeye sevk edildi",
              "İzmir Açıkları'nda 20 düzensiz göçmen kurtarıldı"):
        assert redact(t) == t


def test_aftermath_headlines_are_dropped(cfg):
    a = _after(cfg)
    for t in ("Silivri gemi kazasında kaptan tutuklandı",
              "Kazada hayatını kaybedenin cenazesi toprağa verildi",
              "Gemi kazası duruşması başladı",
              "Silivri kazası kayıpların kimlikleri belli oldu",
              "Batan geminin sahibi gözaltına alındı"):
        assert drop_aftermath(_norm(t), a), t


def test_live_hazard_headlines_are_kept(cfg):
    a = _after(cfg)
    for t in ("Marmara'da tekne alabora oldu, 3 kişi kayıp",
              "Zonguldak açıklarında gemi su alıyor",
              "KKTC'deki gemi kazasında can kaybı 13'e yükseldi"):
        assert not drop_aftermath(_norm(t), a), t


def test_news_pipeline_publishes_no_person_name(cfg, monkeypatch):
    """End to end over the cached feeds: whatever survives carries no name."""
    import requests

    from src.ingest import _net, news
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", True)
    monkeypatch.setattr(_net.requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(requests.RequestException("offline")))
    for inc in news.fetch_news(cfg):
        for s in inc.sources:
            assert "Elmas Demir" not in s.detail
            assert "cenaze" not in _norm(s.detail)


def _mangle(s: str) -> str:
    """What a feed looks like when its UTF-8 body gets decoded as latin-1."""
    return s.encode("utf-8").decode("latin-1")


def test_mojibake_is_repaired():
    from src.model import fix_mojibake
    for good in ("SON DAKİKA HABERİ: Silivri'deki kazada gemi battı",
                 "TUĞBERK İMAMOĞLU GEMİSİ", "Çeşme açıklarında fırtına"):
        assert fix_mojibake(_mangle(good)) == good

def test_clean_turkish_is_left_alone():
    from src.model import fix_mojibake
    for t in ("Silivri açıklarında gemi battı", "Marmara'da fırtına", "Şile İğneada Çeşme", ""):
        assert fix_mojibake(t) == t


def test_prune_scrubs_names_and_mojibake_already_in_the_store(tmp_path):
    from src.model import Incident, Source, Vessel
    from src.process.prune import scrub_names
    from src.store import Store
    s = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))
    inc = Incident(id="x", lat=41.0, lon=29.0, vessel=Vessel(name="Tuğberk İmamoğlu"))
    inc.sources.append(Source(kind="news", detail="Elmas Demir'in cenazesi kaldırıldı"))
    inc.sources.append(Source(kind="news", detail=_mangle("SON DAKİKA: Tuğberk İmamoğlu'nun mürettebatı")))
    s.upsert_incident(inc)
    assert scrub_names(s) == 2
    details = [x.detail for x in s.incidents["x"].sources]
    assert "Elmas Demir" not in details[0] and REDACTED in details[0]
    assert details[1] == "SON DAKİKA: Tuğberk İmamoğlu'nun mürettebatı"   # vessel name kept


def test_single_surname_with_victim_context_is_redacted():
    t = "KKTC'deki kazada hayatını kaybeden Demir'in cenazesi Eskişehir'e getirildi"
    assert "Demir" not in redact(t) and REDACTED in redact(t)


def test_victim_context_does_not_eat_place_names():
    for t in ("Zonguldak açıklarında batan gemide kayıp 3 kişi aranıyor",
              "Marmara'da kaybolan tekne Silivri açıklarında bulundu",
              "Girne'de hayatını kaybeden yolcular için tören düzenlendi"):
        assert REDACTED not in redact(t), t


def test_news_ids_are_stable_across_processes(cfg, monkeypatch):
    """hash() is salted per process; ids built on it changed every CI run."""
    import requests

    from src.ingest import _net, news
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", True)
    monkeypatch.setattr(_net.requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(requests.RequestException("offline")))
    ids = {i.id for i in news.fetch_news(cfg)}
    assert ids
    assert ids == {i.id for i in news.fetch_news(cfg)}
    # sha1-derived, so the same set comes back in a fresh interpreter too
    assert all(i.startswith("news-") and len(i) == 15 for i in ids)


def test_prune_drops_aftermath_already_in_the_store(cfg, tmp_path):
    from src.model import Incident, Source
    from src.process.prune import drop_stored_aftermath
    from src.store import Store
    s = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))
    for iid, detail, kind in (
            ("a", "Kazada hayatını kaybedenin cenazesi toprağa verildi", "news"),
            ("b", "Marmara'da tekne alabora oldu, 3 kişi kayıp", "news"),
            ("c", "Silivri kazasında kaptan tutuklandı", "news")):
        inc = Incident(id=iid, lat=41.0, lon=29.0)
        inc.sources.append(Source(kind=kind, detail=detail))
        s.upsert_incident(inc)
    assert drop_stored_aftermath(s, cfg) == 2
    assert set(s.incidents) == {"b"}


def test_an_official_source_keeps_an_incident_alive(cfg, tmp_path):
    from src.model import Incident, Source
    from src.process.prune import drop_stored_aftermath
    from src.store import Store
    s = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))
    inc = Incident(id="a", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="news", detail="Kaptan tutuklandı"))
    inc.sources.append(Source(kind="official", detail="Arama kurtarma sürüyor"))
    s.upsert_incident(inc)
    assert drop_stored_aftermath(s, cfg) == 0


def test_shore_accidents_are_excluded(cfg):
    a = [_norm(w) for w in cfg["news"]["exclude_words"]]
    assert drop_aftermath(_norm("İskeleden sığ suya balıklama atlayan tatilci öldü"), a)
    assert not drop_aftermath(_norm("Tekne iskeleye çarptı, 2 yaralı"), a)
