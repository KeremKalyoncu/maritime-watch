import json

from src.model import Incident, Source, Warning
from src.store import Store


def _store(tmp_path):
    return Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))


def test_upsert_new_then_merge_sources(tmp_path):
    s = _store(tmp_path)
    inc = Incident(id="a", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="ais-anomaly", detail="d1"))
    s.upsert_incident(inc)

    inc2 = Incident(id="a", lat=41.0, lon=29.0)
    inc2.sources.append(Source(kind="official", org="SG", detail="d2"))
    s.upsert_incident(inc2)

    assert len(s.incidents["a"].sources) == 2


def test_warning_same_id_refreshes_not_duplicates(tmp_path):
    s = _store(tmp_path)
    assert s.upsert_warning(Warning(id="w1", headline="dalga ~2.7 m", org="Open-Meteo",
                                    value=2.7))[1] == "new"
    cur, how = s.upsert_warning(Warning(id="w1", headline="dalga ~0.4 m", org="Open-Meteo",
                                        value=0.4))
    assert how == "refreshed"
    assert cur.headline == "dalga ~0.4 m" and cur.value == 0.4   # live figure updated
    assert len(cur.orgs) == 1                                    # not counted as 2 sources


def test_same_org_refetch_is_not_a_confirmation(tmp_path):
    s = _store(tmp_path)
    s.upsert_warning(Warning(id="om-antalya", headline="dalga ~2.7 m", kind="marine-weather",
                             org="Open-Meteo", area="Antalya Körfezi", value=2.7,
                             lat=36.55, lon=30.6, issued="2026-09-04T01:00:00"))
    cur, how = s.upsert_warning(Warning(id="om-antalya-later", headline="dalga ~0.2 m",
                                        kind="marine-weather", org="Open-Meteo",
                                        area="Antalya Körfezi", value=0.2,
                                        lat=36.55, lon=30.6, issued="2026-09-04T06:00:00"))
    assert how == "refreshed"
    assert len(cur.orgs) == 1


def test_warning_merges_same_hazard_from_two_sources(tmp_path):
    s = _store(tmp_path)
    a = Warning(id="eq-afad", headline="Deprem M4.3 - Marmara", kind="earthquake",
                org="AFAD", lat=40.91, lon=28.24, value=4.3, issued="2026-09-04T09:12:33")
    b = Warning(id="eq-usgs", headline="Deprem M4.2 - Sea of Marmara", kind="earthquake",
                org="USGS", lat=40.91, lon=28.25, value=4.2, issued="2026-09-04T09:13:00")
    assert s.upsert_warning(a)[1] == "new"
    cur, how = s.upsert_warning(b)
    assert how == "merged"
    assert set(cur.orgs) == {"AFAD", "USGS"}
    assert len(s.warnings) == 1


def test_distant_quakes_not_merged(tmp_path):
    s = _store(tmp_path)
    s.upsert_warning(Warning(id="q1", headline="x", kind="earthquake", org="AFAD",
                             lat=40.9, lon=28.2, value=4.3, issued="2026-09-04T09:12:00"))
    _, how = s.upsert_warning(Warning(id="q2", headline="y", kind="earthquake", org="USGS",
                                      lat=36.8, lon=27.3, value=4.1, issued="2026-09-04T09:12:30"))
    assert how == "new"
    assert len(s.warnings) == 2


def test_save_and_reload(tmp_path):
    s = _store(tmp_path)
    inc = Incident(id="a", lat=41.0, lon=29.0, type="drift")
    inc.sources.append(Source(kind="official", org="SG", detail="x"))
    s.upsert_incident(inc)
    s.upsert_warning(Warning(id="w1", headline="h", area="Marmara Denizi"))
    s.save()

    s2 = _store(tmp_path)
    assert s2.incidents["a"].type == "drift"
    assert s2.warnings["w1"].area == "Marmara Denizi"

    raw = json.loads((tmp_path / "web" / "data" / "incidents.json").read_text("utf-8"))
    assert raw[0]["id"] == "a"


def test_event_log_written(tmp_path):
    s = _store(tmp_path)
    s.upsert_incident(Incident(id="a", lat=1.0, lon=2.0))
    log = (tmp_path / "data" / "events.jsonl").read_text("utf-8").strip().splitlines()
    assert json.loads(log[0])["kind"] == "incident_new"
