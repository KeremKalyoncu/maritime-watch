import re

from src.alert.telegram import Notifier, _beaufort, _num
from src.model import Incident, Source, Vessel, Warning

_HEADER = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d  \[|^-{10,}$")


def _notifier(cfg):
    return Notifier(cfg)


def _body(n):
    """outbox.log without the internal '[key]' header / separator lines."""
    return "\n".join(ln for ln in n.outbox.read_text("utf-8").splitlines() if not _HEADER.match(ln))


def test_incident_message_is_plain_turkish(cfg):
    n = _notifier(cfg)
    inc = Incident(id="2026-09-04-x", type="distress", status="confirmed",
                   lat=40.90, lon=28.20, area="Marmara Denizi", casualties=2,
                   vessel=Vessel(name="EGE 5", mmsi=271000001))
    inc.sources.append(Source(kind="official", org="Sahil Güvenlik", detail="tekne battı",
                              url="https://sg.gov.tr/x"))
    n.incident(inc, dry=True)
    body = _body(n)

    # plain-language content
    assert "DENİZDE OLAY — DOĞRULANDI" in body
    assert "tehlike çağrısı" in body            # type translated
    assert "doğrulandı (resmi kaynak)" in body  # status translated
    assert "EGE 5" in body
    assert "2 kişi bildirildi" in body
    assert "deniz mili" in body                 # nearest-port line in plain words
    assert "google.com/maps?q=40.9" in body
    assert "158 Sahil Güvenlik" in body

    # no English jargon / numeric confidence leaking to the user
    for bad in ("distress", "confirmed", "major", "Güven:", "MMSI", "ais-anomaly", "nM "):
        assert bad not in body


def test_sart_always_sends_even_if_status_not_selected(cfg):
    cfg["alert"]["telegram"]["only_status"] = ["confirmed"]
    n = _notifier(cfg)
    inc = Incident(id="sart1", type="distress", status="signal", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="ais-sart", org="AIS", detail="AIS-SART sinyali alındı"))
    n.incident(inc, dry=True)
    assert "sart1" in "".join(n._sent)
    assert "TEHLİKE İŞARETİ ALINDI" in n.outbox.read_text("utf-8")


def test_probable_incident_sends_with_soft_wording(cfg):
    n = _notifier(cfg)
    inc = Incident(id="p1", type="drift", status="probable", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="ais-anomaly", detail="gap"))
    inc.sources.append(Source(kind="news", org="yerel", detail="haber"))
    n.incident(inc, dry=True)
    log = n.outbox.read_text("utf-8")
    assert "henüz doğrulanmadı" in log
    assert "sürüklenme" in log                 # type_tr("drift")


def test_weather_warning_has_beaufort(cfg):
    n = _notifier(cfg)
    w = Warning(id="w1", headline="Marmara Denizi: dalga ~2.6 m, rüzgar hamlesi ~41 kn (36 saat)",
                area="Marmara Denizi", kind="marine-weather", severity="major",
                org="Open-Meteo", value=2.6, lat=40.7, lon=28.3)
    n.warning(w, dry=True)
    log = n.outbox.read_text("utf-8")
    assert "DENİZ HAVA UYARISI" in log
    assert "2,6 metre" in log
    assert "Bofor" in log
    assert "Küçük tekneyle denize çıkmayın" in log
    assert "kn" not in log or "knot" in log     # raw "kn" abbreviation not shown bare


def test_multi_source_confirmation_message(cfg):
    n = _notifier(cfg)
    w = Warning(id="eq1", headline="Deprem M4.2 - Marmara", kind="earthquake",
                org="AFAD", value=4.2, lat=40.9, lon=28.2)
    w.add_source(Source(kind="earthquake", org="USGS", detail="M4.1"))
    w.add_source(Source(kind="earthquake", org="EMSC", detail="M4.3"))
    n.warning_confirmed(w, dry=True)
    log = n.outbox.read_text("utf-8")
    assert "3 ayrı kaynak" in log
    assert "AFAD" in log and "USGS" in log and "EMSC" in log


def test_helpers():
    assert _num(2.6) == "2,6"
    assert _num(2.0) == "2"
    assert _beaufort(41) == 9 or _beaufort(41) == 8


def test_digest_batches_into_one_message(cfg):
    cfg["alert"]["telegram"]["digest"] = True
    n = _notifier(cfg)
    for i in range(3):
        w = Warning(id=f"w{i}", headline=f"uyari {i}", kind="marine-weather",
                    org="Open-Meteo", area="Marmara", lat=40.7, lon=28.3)
        n.warning(w, dry=True)
    assert n._sent == set()          # nothing sent yet, all queued
    assert len(n._queue) == 3
    n.flush(dry=True)
    assert len(n._queue) == 0
    assert {"wx:w0", "wx:w1", "wx:w2"} <= n._sent


def test_digest_sart_bypasses_queue(cfg):
    cfg["alert"]["telegram"]["digest"] = True
    n = _notifier(cfg)
    inc = Incident(id="s9", type="distress", status="signal", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="ais-sart", org="AIS", detail="SART"))
    n.incident(inc, dry=True)
    assert "inc:s9:signal:1" in "".join(n._sent)   # sent immediately, not queued
    assert n._queue == []
