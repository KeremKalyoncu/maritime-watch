from src.model import Incident, Source
from src.process.dedup import correlate, dist_nm
from src.store import Store


def test_dist_nm_known():
    # ~1 degree of latitude ~= 60 nm
    d = dist_nm(40.0, 29.0, 41.0, 29.0)
    assert 58 < d < 62


def test_dist_nm_missing_is_huge():
    assert dist_nm(None, 29.0, 41.0, 29.0) > 1000


def test_correlate_merges_nearby(tmp_path):
    store = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))
    a = Incident(id="a", lat=41.00, lon=29.00)
    a.sources.append(Source(kind="ais-anomaly", detail="speed-drop"))
    store.upsert_incident(a)

    b = Incident(id="b", lat=41.03, lon=29.02)   # ~2 nm away
    b.sources.append(Source(kind="official", org="SG", detail="tekne sürüklendi"))
    merged = correlate(store, b)

    assert merged.id == "a"
    assert {s.kind for s in merged.sources} == {"ais-anomaly", "official"}


def test_correlate_keeps_far_apart_separate(tmp_path):
    store = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))
    a = Incident(id="a", lat=41.0, lon=29.0)
    a.sources.append(Source(kind="ais-anomaly", detail="x"))
    store.upsert_incident(a)

    b = Incident(id="b", lat=36.8, lon=30.7)      # Antalya, far
    b.sources.append(Source(kind="official", org="SG", detail="y"))
    assert correlate(store, b).id == "b"


def test_correlate_matches_by_vessel_name_without_coords(tmp_path):
    from src.model import Vessel
    store = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))
    a = Incident(id="a", lat=41.07, lon=28.25, vessel=Vessel(name="ALSU"))
    a.sources.append(Source(kind="news", org="aa", detail="ALSU gemisi kazası"))
    store.upsert_incident(a)

    b = Incident(id="b", vessel=Vessel(name="Alsu"))     # no coords, different case
    b.sources.append(Source(kind="official", org="SG", detail="ALSU gemisi kaptanı tutuklandı"))
    merged = correlate(store, b)
    assert merged.id == "a"
    assert {s.org for s in merged.sources} == {"aa", "SG"}


def test_correlate_matches_by_shared_place(tmp_path):
    store = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))
    a = Incident(id="a", lat=41.07, lon=28.25, area="Marmara Denizi", places=["Silivri"])
    a.sources.append(Source(kind="news", org="ntv", detail="Silivri gemi kazası"))
    store.upsert_incident(a)

    b = Incident(id="b", lat=41.09, lon=28.30, area="Marmara Denizi", places=["Silivri"])
    b.sources.append(Source(kind="news", org="hurriyet", detail="Silivri'de kayıplar aranıyor"))
    assert correlate(store, b).id == "a"
