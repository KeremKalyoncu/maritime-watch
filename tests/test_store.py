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


def test_warning_dedup(tmp_path):
    s = _store(tmp_path)
    w = Warning(id="w1", headline="h")
    assert s.upsert_warning(w) is True
    assert s.upsert_warning(Warning(id="w1", headline="h")) is False


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
