"""Regressions for the production bugs found on the live channel:
state had to survive between CI runs, and messages had to stop repeating,
mislabelling the type, or inventing a "~0 deniz mili" distance."""

import json
import time

from src.alert.telegram import Notifier
from src.model import Incident, Source, Vessel
from src.process.anomaly import VesselState
from src.process.dedup import correlate
from src.process.extract import incident_type
from src.store import Store


def _ago(hours):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - hours * 3600))


def _store(tmp_path):
    return Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))


# ---- state survives a fresh checkout -------------------------------------
def test_sent_keys_are_capped(cfg, monkeypatch):
    import src.alert.telegram as tg
    monkeypatch.setattr(tg, "_SENT_CAP", 10)
    n = Notifier(cfg)
    for i in range(25):
        n._remember(f"k{i:03d}")
    assert len(n._sent) <= 10
    assert len(json.loads(n.sent_path.read_text("utf-8"))) <= 10


def test_vessel_state_prunes_old_and_caps(tmp_path):
    vs = VesselState(str(tmp_path / "v.json"), 20)
    vs.update([{"mmsi": 1, "lat": 41.0, "lon": 29.0, "sog": 5, "ts": _ago(1)}])
    vs.update([{"mmsi": 2, "lat": 41.0, "lon": 29.0, "sog": 5, "ts": _ago(30)}])
    dropped = vs.prune(ttl_hours=12)
    assert dropped == 1
    assert "1" in vs.data and "2" not in vs.data


def test_event_log_is_trimmed(tmp_path):
    s = _store(tmp_path)
    for i in range(50):
        s.upsert_incident(Incident(id=f"i{i}", lat=41.0, lon=29.0))
    removed = s.trim_events(max_lines=10)
    assert removed == 40
    assert len(s.events_path.read_text("utf-8").strip().splitlines()) == 10


# ---- message quality ------------------------------------------------------
def test_incident_type_is_inferred_from_wording():
    assert incident_type("Muğla açıklarında 2 şahıs kurtarılmıştır") == "distress"
    assert incident_type("balıkçı teknesi alabora oldu") == "capsize"
    assert incident_type("tanker karaya oturdu") == "grounding"
    assert incident_type("iki gemi çarpıştı") == "collision"
    assert incident_type("Merkez Bankası faiz kararı") == "unknown"


def test_coarse_location_avoids_zero_mile_nonsense(cfg):
    n = Notifier(cfg)
    inc = Incident(id="c1", type="distress", status="confirmed",
                   lat=40.98, lon=27.51, area="Marmara Denizi", coarse=True)
    inc.sources.append(Source(kind="official", org="SG", detail="Tekirdağ açıklarında kurtarma",
                              url="https://sg.gov.tr/a"))
    n.incident(inc, dry=True)
    body = n.outbox.read_text("utf-8")
    assert "Tekirdağ açıkları" in body
    assert "deniz mili" not in body


# ---- correlation must not fuse separate official announcements ------------
def test_two_official_announcements_same_city_stay_separate(tmp_path):
    s = _store(tmp_path)
    a = Incident(id="a", lat=38.43, lon=27.14, area="Güney Ege", places=["Izmir"], coarse=True)
    a.sources.append(Source(kind="official", org="SG", detail="İzmir önlerinde 2 şahıs",
                            url="https://sg.gov.tr/izmir-2-sahis"))
    s.upsert_incident(a)

    b = Incident(id="b", lat=38.43, lon=27.14, area="Güney Ege", places=["Izmir"], coarse=True,
                 casualties=20)
    b.sources.append(Source(kind="official", org="SG", detail="İzmir açıklarında 20 göçmen",
                            url="https://sg.gov.tr/izmir-20-gocmen"))
    assert correlate(s, b).id == "b"          # separate events, separate cards


def test_news_about_one_story_still_merges(tmp_path):
    s = _store(tmp_path)
    a = Incident(id="a", lat=41.07, lon=28.25, area="Marmara Denizi", places=["Silivri"], coarse=True)
    a.sources.append(Source(kind="news", org="aa", detail="Silivri'de gemi kazası"))
    s.upsert_incident(a)

    b = Incident(id="b", lat=41.07, lon=28.25, area="Marmara Denizi", places=["Silivri"], coarse=True)
    b.sources.append(Source(kind="news", org="ntv", detail="Silivri kazasında son durum"))
    assert correlate(s, b).id == "a"


def test_ais_fix_still_merges_with_coarse_news(tmp_path):
    s = _store(tmp_path)
    a = Incident(id="a", lat=41.05, lon=28.20, vessel=Vessel(mmsi=271000001))   # precise AIS fix
    a.sources.append(Source(kind="ais-anomaly", org="AIS", detail="speed-drop"))
    s.upsert_incident(a)

    b = Incident(id="b", lat=41.07, lon=28.25, places=["Silivri"], coarse=True)
    b.sources.append(Source(kind="news", org="aa", detail="Silivri açıklarında tekne"))
    assert correlate(s, b).id == "a"


def test_every_source_is_shown_so_the_count_is_traceable(cfg):
    n = Notifier(cfg)
    inc = Incident(id="m1", type="distress", status="confirmed", lat=38.43, lon=27.14,
                   area="Güney Ege", coarse=True, casualties=20)
    inc.sources.append(Source(kind="official", org="SG", detail="İzmir önlerinde 2 şahıs",
                              url="https://sg.gov.tr/a"))
    inc.sources.append(Source(kind="official", org="SG", detail="İzmir açıklarında 20 göçmen",
                              url="https://sg.gov.tr/b"))
    n.incident(inc, dry=True)
    body = n.outbox.read_text("utf-8")
    assert "Kaynaklar (2)" in body
    assert "2 şahıs" in body and "20 göçmen" in body        # both quotes visible
    assert "en yüksek sayı" in body                          # the 20 is explained
