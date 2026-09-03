from src.model import Incident, Source
from src.process.classify import area_centroid, area_of, classify, nearest_port, place_hint


def test_area_of_bosphorus():
    assert area_of(41.12, 29.05) == "İstanbul Boğazı"


def test_area_of_open_sea_fallback():
    assert area_of(37.0, 25.5) in ("Güney Ege", "Kuzey Ege", "Türk karasuları civarı")


def test_place_hint():
    lat, lon, area = place_hint("Çeşme açıklarında lastik botta 12 göçmen kurtarıldı")
    assert lat is not None and lon is not None
    assert area


def test_place_hint_turkish_capital_i():
    # "İzmir".lower() is 'i̇zmir' in Python — the matcher must still find it
    lat, lon, _ = place_hint("02.09.2026 İzmir Açıklarında 20 Düzensiz Göçmen Kurtarılmıştır")
    assert (lat, lon) == (38.43, 27.14)


def test_area_centroid_named():
    lat, lon = area_centroid("Marmara Denizi")
    assert 40.0 < lat < 41.5 and 26.0 < lon < 30.5


def test_status_signal_for_ais_only():
    inc = Incident(id="a", lat=41.1, lon=29.0)
    inc.sources.append(Source(kind="ais-anomaly", detail="nav-status"))
    classify(inc)
    assert inc.status == "signal"
    assert inc.confidence < 0.5


def test_status_confirmed_for_official():
    inc = Incident(id="b", lat=38.3, lon=26.3)
    inc.sources.append(Source(kind="official", org="SG", detail="kurtarıldı"))
    classify(inc)
    assert inc.status == "confirmed"
    assert inc.severity == "major"


def test_status_probable_for_ais_plus_news():
    inc = Incident(id="c", lat=42.0, lon=30.0)
    inc.sources.append(Source(kind="ais-anomaly", detail="gap"))
    inc.sources.append(Source(kind="news", org="X", detail="haber"))
    classify(inc)
    assert inc.status == "probable"


def test_casualties_make_it_critical():
    inc = Incident(id="d", lat=38.3, lon=26.3, casualties=3)
    inc.sources.append(Source(kind="official", org="SG", detail="3 kayıp"))
    classify(inc)
    assert inc.severity == "critical"


def test_resolved_is_sticky():
    inc = Incident(id="e", lat=38.3, lon=26.3, status="resolved")
    inc.sources.append(Source(kind="official", org="SG", detail="x"))
    classify(inc)
    assert inc.status == "resolved"


def test_ais_sart_is_probable():
    inc = Incident(id="s", lat=40.8, lon=28.6)
    inc.sources.append(Source(kind="ais-sart", org="AIS", detail="MOB"))
    classify(inc)
    assert inc.status == "probable"


def test_nearest_port():
    name, nm, direction = nearest_port(41.02, 28.30)   # off Silivri
    assert name in ("Silivri", "İstanbul", "Tekirdağ")
    assert nm < 40
    assert direction in ("K", "KKD", "KD", "DKD", "D", "DGD", "GD", "GGD",
                         "G", "GGB", "GB", "BGB", "B", "BKB", "KB", "KKB")


def test_nearest_port_none_for_missing_coords():
    assert nearest_port(None, 28.0) is None
