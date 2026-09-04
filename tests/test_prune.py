import time

from src.model import Incident, Source, Warning
from src.process.prune import prune
from src.store import Store


def _store(tmp_path):
    return Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))


def _ago(hours):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - hours * 3600))


def test_stale_weather_warning_expires(tmp_path):
    s = _store(tmp_path)
    fresh = Warning(id="w-new", headline="h", kind="marine-weather", org="Open-Meteo")
    fresh.last_update = _ago(2)
    old = Warning(id="w-old", headline="h", kind="marine-weather", org="Open-Meteo")
    old.last_update = _ago(30)
    s.warnings["w-new"], s.warnings["w-old"] = fresh, old

    dw, _ = prune(s)
    assert dw == 1
    assert "w-new" in s.warnings and "w-old" not in s.warnings


def test_old_confirmed_incident_auto_resolves(tmp_path):
    s = _store(tmp_path)
    inc = Incident(id="i1", status="confirmed", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="official", org="SG", detail="x"))
    inc.last_update = _ago(100)
    s.incidents["i1"] = inc

    prune(s)
    assert s.incidents["i1"].status == "resolved"


def test_official_resolution_phrase_closes_incident(tmp_path):
    s = _store(tmp_path)
    inc = Incident(id="i9", status="confirmed", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="official", org="SG",
                              detail="Silivri açıklarında arama kurtarma operasyonu tamamlandı"))
    inc.last_update = _ago(1)          # recent, would NOT time out
    s.incidents["i9"] = inc
    prune(s)
    assert s.incidents["i9"].status == "resolved"


def test_plain_rescue_report_stays_open(tmp_path):
    s = _store(tmp_path)
    inc = Incident(id="i10", status="confirmed", lat=41.0, lon=29.0)
    inc.sources.append(Source(kind="official", org="SG",
                              detail="Muğla açıklarında 2 şahıs kurtarıldı"))
    inc.last_update = _ago(1)
    s.incidents["i10"] = inc
    prune(s)
    assert s.incidents["i10"].status == "confirmed"   # "kurtarıldı" alone is not terminal


def test_old_signal_incident_is_removed(tmp_path):
    s = _store(tmp_path)
    inc = Incident(id="i2", status="signal", lat=41.0, lon=29.0)
    inc.last_update = _ago(20)
    s.incidents["i2"] = inc

    _, di = prune(s)
    assert di == 1 and "i2" not in s.incidents


def test_seed_dropped_once_real_data_exists(tmp_path):
    s = _store(tmp_path)
    seed = Incident(id="2026-09-03-seed-ais01", status="signal", lat=41.1, lon=29.0)
    seed.last_update = _ago(1)
    real = Incident(id="2026-09-04-rep-abc", status="confirmed", lat=40.9, lon=28.2)
    real.sources.append(Source(kind="official", org="SG", detail="x"))
    real.last_update = _ago(1)
    s.incidents[seed.id], s.incidents[real.id] = seed, real

    prune(s)
    assert seed.id not in s.incidents and real.id in s.incidents


def test_seed_kept_when_no_real_data(tmp_path):
    s = _store(tmp_path)
    seed = Warning(id="wx-marmaradenizi-seed", headline="h", kind="marine-weather", org="MGM")
    seed.last_update = _ago(1)
    s.warnings[seed.id] = seed

    prune(s)
    assert seed.id in s.warnings   # fresh clone / no live data yet -> keep the demo
