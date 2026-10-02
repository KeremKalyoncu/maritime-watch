"""People rescued are not casualties.

Every routine Coast Guard release ("34 Düzensiz Göçmen Kurtarılmıştır") was read
as casualties=34, which made it severity "critical" on the public map and sent it
out as an emergency. A count now goes to `casualties` only when the wording says
the people are harmed, missing or still at risk, and to `rescued` when it says
they were rescued or evacuated.
"""

import json

import pytest

from src.model import Incident, Source
from src.process.classify import classify
from src.process.dedup import correlate
from src.process.extract import extract
from src.process.prune import backfill
from src.render.feed import build_feed
from src.render.geojson import build_incidents_geojson
from src.render.stats import build_stats
from src.store import Store

SG_RESCUE = "01.10.2026 İzmir Açıklarında 34 Düzensiz Göçmen Kurtarılmıştır"


def _store(tmp_path):
    return Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))


def _official(text, iid="rep-x"):
    """Build the incident the way official.py does."""
    ex = extract(text)
    inc = Incident(
        id=iid,
        type=ex.itype,
        lat=ex.lat,
        lon=ex.lon,
        area=ex.area,
        casualties=ex.casualties,
        rescued=ex.rescued,
        places=ex.places,
        coarse=not ex.precise,
    )
    inc.sources.append(Source(kind="official", org="Sahil Güvenlik", detail=text, url="https://sg/" + iid))
    return inc


# ---- extraction ----------------------------------------------------------
def test_official_rescue_counts_as_rescued_not_casualties():
    ex = extract(SG_RESCUE)
    assert ex.rescued == 34
    assert ex.casualties is None


def test_rescued_and_missing_in_one_sentence_are_kept_apart():
    ex = extract("2 kişi kurtarıldı, 1 balıkçı kayıp")
    assert ex.rescued == 2
    assert ex.casualties == 1


@pytest.mark.parametrize(
    "text, casualties, rescued",
    [
        ("3 kişi hayatını kaybetti", 3, None),
        ("Zonguldak açıklarında batan gemide kayıp 3 kişi aranıyor", 3, None),
        ("Marmara'da tekne alabora oldu, 3 kişi kayıp", 3, None),
        ("Fırtınada 4 kişi yaralandı", 4, None),
        ("Gece çıkan 2 balıkçı kayboldu", 2, None),
        ("Adada 6 kişi mahsur kaldı", 6, None),
        ("Gemide 1 denizci öldü", 1, None),
        ("12 mürettebat tahliye edildi", None, 12),
        ("Çeşme açıklarında lastik botta mahsur kalan 12 düzensiz göçmen kurtarıldı", None, 12),
        ("Mudanya açıklarında sürüklenen tekne ve içindeki 4 kişi kurtarıldı", None, 4),
        # "öl" inside "bölgesinde" is not a death
        ("12 göçmen Çeşme bölgesinde kurtarıldı", None, 12),
        # a count with no verb says nothing about harm: unknown stays unknown
        ("Bodrum açıklarında teknedeki 4 kişi", None, None),
        # boat capacity, not people
        ("5 kişilik tekne battı", None, None),
        # the harm word belongs to the nearest count, not to the capacity before it
        ("50 kişilik teknede 2 kişi kayıp", 2, None),
        ("Merkez Bankası faiz kararını açıkladı", None, None),
        # headlines seen in production (data/events.jsonl)
        ("08.09.2026 İzmir Açıklarında 18 Düzensiz Göçmen (Beraberinde 1 Çocuk) Kurtarılmıştır", None, 18),
        ("Kayıp 10 denizci nerede?", 10, None),
        ("Silivri açıklarındaki gemi faciasında 12'nci gün: Kayıp 10 mürettebat aranıyor", 10, None),
        ("Batan gemideki 10 denizciyi arama çalışmaları 11. gününde", 10, None),
        ("Milas açıklarında lastik botta 23 kaçak göçmen yakalandı", None, None),
        ("Şile açıklarında su alan 18 metrelik balıkçı teknesi botumuzca kurtarıldı", None, None),
        # the first outcome word decides: the boat was saved, the 2 are missing
        ("2 kişi kayıp, tekne kurtarıldı", 2, None),
        ("kayıp 2 balıkçı sağ olarak kurtarıldı", None, 2),
        ("3 kişi kurtarılamadı", 3, None),
        ("18 göçmen (2'si ölü) kıyıya çıkarılarak kurtarıldı", 18, None),
        ("34 düzensiz göçmen Sahil Güvenlik arama kurtarma botuyla kurtarıldı", None, 34),
        ("09.09.2026 İZMİR AÇIKLARINDA 2 ÇOCUK KURTARILMIŞTIR", None, 2),
    ],
)
def test_extracted_people_counts(text, casualties, rescued):
    ex = extract(text)
    assert (ex.casualties, ex.rescued) == (casualties, rescued)


# ---- severity --------------------------------------------------------------
def test_confirmed_official_rescue_is_major_not_critical():
    inc = classify(_official(SG_RESCUE))
    assert inc.status == "confirmed"
    assert inc.rescued == 34 and inc.casualties is None
    assert inc.severity == "major"


def test_rescue_with_someone_still_missing_is_critical():
    inc = classify(_official("Tekne battı: 2 kişi kurtarıldı, 1 balıkçı kayıp"))
    assert (inc.rescued, inc.casualties) == (2, 1)
    assert inc.severity == "critical"


def test_rescued_only_news_is_not_critical():
    inc = Incident(id="n", lat=38.3, lon=26.3, rescued=5)
    inc.sources.append(Source(kind="news", org="aa", detail="5 kişi kurtarıldı"))
    classify(inc)
    assert inc.severity == "minor"


# ---- merging ---------------------------------------------------------------
def test_store_upsert_keeps_both_counts(tmp_path):
    s = _store(tmp_path)
    a = Incident(id="a", lat=41.0, lon=29.0, casualties=1)
    a.sources.append(Source(kind="news", org="aa", detail="1 balıkçı kayıp"))
    s.upsert_incident(a)

    b = Incident(id="a", lat=41.0, lon=29.0, rescued=2)
    b.sources.append(Source(kind="news", org="ntv", detail="2 kişi kurtarıldı"))
    got = s.upsert_incident(b)
    assert (got.casualties, got.rescued) == (1, 2)


def test_correlate_merges_both_counts_with_max(tmp_path):
    s = _store(tmp_path)
    a = Incident(id="a", lat=41.07, lon=28.25, places=["Silivri"], casualties=1, rescued=2)
    a.sources.append(Source(kind="news", org="aa", detail="Silivri'de tekne battı"))
    s.upsert_incident(a)

    b = Incident(id="b", lat=41.07, lon=28.25, places=["Silivri"], casualties=3, rescued=1)
    b.sources.append(Source(kind="news", org="ntv", detail="Silivri kazasında son durum"))
    got = correlate(s, b)
    assert got.id == "a"
    assert (got.casualties, got.rescued) == (3, 2)


# ---- stored data -----------------------------------------------------------
def test_old_stored_incident_without_rescued_still_loads():
    old = Incident(id="old", casualties=2).to_dict()
    del old["rescued"]
    inc = Incident.from_dict(old)
    assert inc.rescued is None and inc.casualties == 2
    assert Incident.from_dict(Incident(id="new", rescued=7).to_dict()).rescued == 7


def test_backfill_moves_a_rescue_count_misread_as_casualties(tmp_path):
    """Records stored before the split carry casualties=34 for a rescue and stay
    critical until they age out; the backfill re-reads the headline and moves it."""
    s = _store(tmp_path)
    legacy = _official(SG_RESCUE, "rep-legacy")
    legacy.casualties, legacy.rescued = 34, None  # what the old extractor stored
    s.upsert_incident(legacy)

    backfill(s)
    got = classify(s.incidents["rep-legacy"])
    assert (got.casualties, got.rescued) == (None, 34)
    assert got.severity == "major"


def test_backfill_leaves_a_real_casualty_count_alone(tmp_path):
    s = _store(tmp_path)
    inc = _official("Tekne battı: 2 kişi kurtarıldı, 1 balıkçı kayıp", "rep-real")
    inc.rescued = None  # stored before the split
    s.upsert_incident(inc)

    backfill(s)
    got = s.incidents["rep-real"]
    assert (got.casualties, got.rescued) == (1, 2)


# ---- outputs ---------------------------------------------------------------
def test_feed_and_geojson_report_rescued_separately(tmp_path):
    s = _store(tmp_path)
    inc = Incident(id="a", lat=38.4, lon=26.9, casualties=1, rescued=2)
    inc.sources.append(Source(kind="official", org="SG", detail="2 kişi kurtarıldı, 1 balıkçı kayıp"))
    s.upsert_incident(inc)

    build_feed(s, str(tmp_path))
    xml = (tmp_path / "feed.xml").read_text("utf-8")
    assert "Kayıp/yaralı: 1" in xml
    assert "Kurtarılan: 2" in xml
    assert "Bildirilen kişi" not in xml

    props = build_incidents_geojson(s)["features"][0]["properties"]
    assert (props["casualties"], props["rescued"]) == (1, 2)


def test_stats_keep_rescued_out_of_the_casualty_total(tmp_path):
    log = tmp_path / "events.jsonl"
    rescue = _official(SG_RESCUE, "rep-new").to_dict()
    legacy = _official("02.10.2026 Çeşme Açıklarında 20 Düzensiz Göçmen Kurtarılmıştır", "rep-old").to_dict()
    legacy["casualties"] = 20  # written by the old extractor, before `rescued` existed
    del legacy["rescued"]
    harm = Incident(id="news-x", casualties=3).to_dict()
    lines = [{"kind": "incident_new", "payload": p} for p in (rescue, legacy, harm)]
    log.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")

    st = build_stats(str(log), str(tmp_path))
    assert st["casualties_reported_total"] == 3
    assert st["incidents_with_casualties"] == 1
    assert st["rescued_reported_total"] == 54
