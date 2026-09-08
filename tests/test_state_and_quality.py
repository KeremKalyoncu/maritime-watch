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
    # a finished rescue is not a distress call; the channel announced completed
    # rescues as "tehlike çağrısı"
    assert incident_type("Muğla açıklarında 2 şahıs kurtarılmıştır") == "rescue"
    assert incident_type("mahsur kalan 12 göçmen için arama kurtarma sürüyor") == "distress"
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


# ---- the committed state must stay small and git-friendly ------------------
def test_vessel_state_is_compact_and_stable_on_disk(tmp_path):
    """This file is committed every cycle. One unsorted line of 16-digit floats
    and nanosecond timestamps makes git rewrite the whole blob each time."""
    vs = VesselState(str(tmp_path / "v.json"), 5)
    for mmsi in (300, 100, 200):
        vs.update([{"mmsi": mmsi, "lat": 40.76105833333334, "lon": 28.929850000001,
                    "sog": 0.31111, "cog": 249.7333,
                    "ts": "2026-09-04 21:36:32.547386925 +0000 UTC"}])
    vs.save()
    raw = (tmp_path / "v.json").read_text("utf-8")

    assert "40.7611" in raw and "40.76105833333334" not in raw     # 4 dp is AIS resolution
    assert "2026-09-04T21:36:32Z" in raw and "547386925" not in raw
    assert raw.count("\n") == 2                                     # one line per vessel
    assert raw.index('"100"') < raw.index('"200"') < raw.index('"300"')   # sorted

    again = VesselState(str(tmp_path / "v.json"), 5)                # still valid JSON
    assert set(again.data) == {"100", "200", "300"}


def test_vessel_track_is_capped_to_what_the_rules_read(tmp_path):
    vs = VesselState(str(tmp_path / "v.json"), 5)
    for i in range(20):
        vs.update([{"mmsi": 1, "lat": 41.0, "lon": 29.0, "sog": 5,
                    "ts": f"2026-09-05T10:{i:02d}:00Z"}])
    assert len(vs.data["1"]["track"]) == 5


def test_map_json_is_written_in_stable_id_order(tmp_path):
    s = _store(tmp_path)
    for iid in ("c", "a", "b"):
        s.upsert_incident(Incident(id=iid, lat=41.0, lon=29.0))
    s.save()
    ids = [i["id"] for i in json.loads((tmp_path / "web" / "data" / "incidents.json").read_text("utf-8"))]
    assert ids == ["a", "b", "c"]


def test_backfill_repairs_records_parsed_by_an_older_extractor(tmp_path):
    """A report taken in before the extractor knew a place kept showing 'belirsiz'
    with no pin, and never came back through ingest."""
    from src.process.prune import backfill
    s = _store(tmp_path)
    inc = Incident(id="rep-old")
    inc.sources.append(Source(kind="official",
                              detail="03.09.2026 Muğla Açıklarında 2 Şahıs Kurtarılmıştır"))
    s.upsert_incident(inc)
    assert backfill(s) > 0
    got = s.incidents["rep-old"]
    assert got.lat is not None and got.lon is not None
    assert got.type != "unknown" and got.area


def test_backfill_keeps_a_position_someone_already_established(tmp_path):
    from src.process.prune import backfill
    s = _store(tmp_path)
    inc = Incident(id="rep-set", type="collision", lat=41.5, lon=28.5, area="Marmara Denizi")
    inc.sources.append(Source(kind="official", detail="Zonguldak açıklarında gemi su alıyor"))
    s.upsert_incident(inc)
    backfill(s)
    got = s.incidents["rep-set"]
    assert (got.lat, got.lon, got.area) == (41.5, 28.5, "Marmara Denizi")
    # the type is text-derived, so a better parse of the same headline wins
    assert got.type == "sinking"


def test_backfill_leaves_an_ais_driven_type_alone(tmp_path):
    from src.process.prune import backfill
    s = _store(tmp_path)
    inc = Incident(id="ais-1", type="drift", lat=41.5, lon=28.5)
    inc.sources.append(Source(kind="ais-anomaly", org="AIS", detail="ais-gap: sinyal kesildi"))
    inc.sources.append(Source(kind="news", detail="Zonguldak açıklarında gemi su alıyor"))
    s.upsert_incident(inc)
    backfill(s)
    assert s.incidents["ais-1"].type == "drift"


def _wx(wid, area="Marmara Denizi", kind="marine-weather"):
    from src.model import Warning
    return Warning(id=wid, headline=f"{area}: fırtına", area=area, kind=kind,
                   severity="major", org="Open-Meteo")


def test_a_warning_the_forecast_no_longer_lists_is_lifted(tmp_path):
    """The gale used to sit on the channel for its whole 18-hour TTL after the
    wind dropped, so nobody learned when it was safe to go back out."""
    from src.process.prune import clear_passed_weather
    s = _store(tmp_path)
    for w in (_wx("wx-a"), _wx("wx-b", "Kuzey Ege")):
        s.upsert_warning(w)
    gone = clear_passed_weather(s, {"wx-a"}, live_sources=True)
    assert [w.id for w in gone] == ["wx-b"]
    assert set(s.warnings) == {"wx-a"}


def test_a_dead_forecast_never_counts_as_all_clear(tmp_path):
    from src.process.prune import clear_passed_weather
    s = _store(tmp_path)
    s.upsert_warning(_wx("wx-a"))
    assert clear_passed_weather(s, set(), live_sources=False) == []
    assert set(s.warnings) == {"wx-a"}


def test_earthquakes_are_never_lifted_this_way(tmp_path):
    from src.model import Warning
    from src.process.prune import clear_passed_weather
    s = _store(tmp_path)
    s.upsert_warning(Warning(id="eq-1", headline="Deprem M4.2", area="Ege Denizi",
                             kind="earthquake", org="AFAD"))
    assert clear_passed_weather(s, set(), live_sources=True) == []


def test_all_clear_message_names_the_area(tmp_path, cfg):
    cfg["secrets"] = {"telegram_token": "", "telegram_chat_id": "", "aisstream_key": ""}
    cfg["alert"]["telegram"]["digest"] = False
    n = Notifier(cfg)
    sent = []
    n._send_one = lambda key, text, dry, lat=None, lon=None: sent.append(text)
    n.weather_passed(_wx("wx-a"), dry=True)
    assert sent and "UYARI KALKTI" in sent[0] and "Marmara Denizi" in sent[0]


def test_a_source_is_never_counted_twice(tmp_path):
    from src.process.prune import dedupe_sources
    s = _store(tmp_path)
    inc = Incident(id="x", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="news", org="cnnturk.com", detail="Silivri'de gemi battı"))
    inc.sources.append(Source(kind="news", org="cnnturk.com", detail="Silivri'de gemi battı"))
    inc.sources.append(Source(kind="news", org="trthaber.com", detail="Silivri'de gemi battı"))
    s.upsert_incident(inc)
    assert dedupe_sources(s) == 1
    assert len(s.incidents["x"].sources) == 2      # two outlets, not three reports
