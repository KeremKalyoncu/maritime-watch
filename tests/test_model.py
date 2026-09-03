from src.model import Incident, Source, Vessel, Warning, make_id


def test_incident_roundtrip():
    inc = Incident(id="x", type="drift", lat=41.0, lon=29.0,
                   vessel=Vessel(name="A", mmsi=1), sources=[Source(kind="ais-anomaly", detail="d")])
    again = Incident.from_dict(inc.to_dict())
    assert again.vessel.mmsi == 1
    assert again.sources[0].kind == "ais-anomaly"
    assert again.to_dict() == inc.to_dict()


def test_warning_roundtrip():
    w = Warning(id="w", headline="h", area="Marmara Denizi", lat=40.7, lon=28.3)
    assert Warning.from_dict(w.to_dict()).to_dict() == w.to_dict()


def test_add_source_dedupes():
    inc = Incident(id="x")
    a = Source(kind="official", org="SG", detail="tekne battı")
    b = Source(kind="official", org="SG", detail="tekne battı")
    assert inc.add_source(a) is True
    assert inc.add_source(b) is False
    assert len(inc.sources) == 1


def test_make_id_stable_per_day():
    i1 = make_id("ais", 41.005, 29.004, "2026-09-03T09:00:00Z")
    i2 = make_id("ais", 41.006, 29.003, "2026-09-03T23:00:00Z")
    assert i1 == i2  # same rounded position, same day
