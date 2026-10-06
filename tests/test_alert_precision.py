"""Three wrong emergencies on the public channel, 04-06.10 (KARARLAR K27). Real headlines.

- 05.10: "İzmir'de evde şüpheli ölüm! … boğazından bıçakla yaralandı, hayatını kaybetti"
  passed the news gate ("boğaz" as a substring of a throat), merged into the Coast
  Guard's İzmir rescue by city name and went out as a confirmed emergency.
- 06.10: "KKTC'de batan yolcu gemisinde 2 kişinin daha cesedine ulaşıldı" (bodies found
  days later) went out as a critical sinking.
- 04.10: an AIS gap merged with the Muğla rescue went out as "AIS sinyali kesildi —
  doğrulandı".
"""

from email.utils import formatdate

import run
from src.ingest import news
from src.model import Incident, Source
from src.process.classify import mentions_strait, place_hint
from src.process.dedup import correlate
from src.process.extract import places
from src.store import Store

STABBING = "İzmir'de evde şüpheli ölüm! 63 yaşındaki adam boğazından bıçakla yaralandı, hayatını kaybetti"
KKTC = "KKTC'de batan yolcu gemisinde 2 kişinin daha cesedine ulaşıldı"
SG_IZMIR = "05.10.2026 İzmir Açıklarında 2 Şahıs Kurtarılmıştır"
SG_MUGLA = "04.10.2026 Muğla Açıklarında 2 Şahıs Kurtarılmıştır"


def _titles(cfg, monkeypatch, *titles):
    now = formatdate(usegmt=True)
    items = "".join(f"<item><title>{t}</title><link>https://example.test/{i}</link><pubDate>{now}</pubDate></item>"
                    for i, t in enumerate(titles))
    cfg["news"]["feeds"] = ["https://example.test/rss"]
    monkeypatch.setattr(news, "fetch_parallel", lambda tasks, **k: [(f"<rss><channel>{items}</channel></rss>", True)])
    return [i.sources[0].detail for i in news.fetch_news(cfg)]


def _store(tmp_path):
    return Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))


def _official(text, iid, lat, lon, place):
    inc = Incident(id=iid, type="rescue", lat=lat, lon=lon, places=[place], coarse=True, rescued=2)
    inc.sources.append(Source(kind="official", org="Sahil Güvenlik", detail=text, url=f"https://sg/{iid}"))
    return inc


def test_bogaz_is_the_strait_not_a_throat():
    for text in ("İstanbul Boğazı'nda gemi arızalandı", "Boğaz’da tekne alabora oldu",
                 "Boğaz trafiği askıya alındı", "Çanakkale Boğazı kapandı", "boğaz"):
        assert mentions_strait(text), text
    for text in (STABBING, "boğazına sarıldı", "boğazını kesti", "boğazında takılı kaldı"):
        assert not mentions_strait(text), text
    assert [name for name, _lat, _lon in places(STABBING)] == ["Izmir"]
    assert place_hint("adam boğazından yaralandı") == (None, None, "")


def test_the_land_crime_and_the_recovered_bodies_never_become_incidents(cfg, monkeypatch):
    kept = _titles(cfg, monkeypatch, STABBING, KKTC,
                   "İstanbul Boğazı'nda makine arızası yapan gemi sürüklendi",
                   "Muğla açıklarında tekne battı, 2 kişi kurtarıldı")
    assert kept == ["İstanbul Boğazı'nda makine arızası yapan gemi sürüklendi",
                    "Muğla açıklarında tekne battı, 2 kişi kurtarıldı"]


def test_an_untyped_headline_does_not_borrow_the_official_badge(tmp_path):
    s = _store(tmp_path)
    story = Incident(id="news-x", lat=38.43, lon=27.14, places=["Izmir"], coarse=True)  # type unknown
    story.sources.append(Source(kind="news", org="hurriyet", detail=STABBING))
    s.upsert_incident(story)
    sg = _official(SG_IZMIR, "rep-izmir", 38.43, 27.14, "Izmir")
    got = correlate(s, sg)
    assert got.id == "rep-izmir" and [x.kind for x in got.sources] == ["official"]
    # the other way round too: the rescue is stored first, the story arrives later
    s2 = _store(tmp_path / "b")
    s2.upsert_incident(_official(SG_IZMIR, "rep-izmir", 38.43, 27.14, "Izmir"))
    late = Incident(id="news-y", lat=38.43, lon=27.14, places=["Izmir"], coarse=True)
    late.sources.append(Source(kind="news", org="hurriyet", detail=STABBING))
    assert correlate(s2, late).id == "news-y"


def test_an_official_notice_names_the_event_and_writes_the_alert(tmp_path):
    s = _store(tmp_path)
    gap = Incident(id="ais-1", type="signal-lost", lat=36.7558, lon=28.0175, area="Güney Ege")
    gap.sources.append(Source(kind="ais-anomaly", org="AIS",
                              detail="ais-gap: seyir halindeyken AIS sinyali yaklaşık 69 dakika önce kesildi"))
    s.upsert_incident(gap)
    sg = _official(SG_MUGLA, "rep-mugla", 36.76, 28.02, "Muğla")
    sg.coarse = False  # within the 8 NM proximity rule
    got = correlate(s, sg)
    assert got.id == "ais-1" and got.type == "rescue"  # not "AIS sinyali kesildi"
    payload = run._alert_payload(got)
    assert payload["description"] == SG_MUGLA and payload["category"] == "rescue"
