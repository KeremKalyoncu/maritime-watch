import time

from src.process.anomaly import VesselState, detect


def _state(tmp_path, history=20):
    return VesselState(str(tmp_path / "vessels.json"), history)


def test_ais_sart_flag(tmp_path, cfg):
    vs = _state(tmp_path)
    pos = [{"mmsi": 972000123, "lat": 40.8, "lon": 28.6, "sog": 0.0, "cog": 0.0,
            "nav_status": 15, "ts": "2026-09-04T09:00:00Z", "name": ""}]
    vs.update(pos)
    out = detect(vs, pos, cfg, {"972000123"})
    sart = [a for a in out if a.kind == "ais-sart"]
    assert sart and sart[0].severity == "critical"
    assert "MOB" in sart[0].detail


def test_safety_message_ignored_by_tracker(tmp_path, cfg):
    vs = _state(tmp_path)
    pos = [{"msg_type": "safety", "mmsi": 271000001, "lat": 41.0, "lon": 29.0,
            "text": "test", "ts": "2026-09-04T09:00:00Z"}]
    vs.update(pos)
    out = detect(vs, pos, cfg, set())
    assert out == []


def test_nav_status_flag(tmp_path, cfg):
    vs = _state(tmp_path)
    pos = [{"mmsi": 111, "lat": 41.1, "lon": 29.0, "sog": 0.1, "cog": 0.0,
            "nav_status": 2, "ts": "2026-09-03T09:00:00Z", "name": "X"}]
    vs.update(pos)
    out = detect(vs, pos, cfg, {"111"})
    kinds = {a.kind for a in out}
    assert "nav-status" in kinds
    assert out[0].mmsi == 111


def test_speed_drop(tmp_path, cfg):
    vs = _state(tmp_path)
    for sog in (10.0, 9.5, 10.2):
        vs.update([{"mmsi": 222, "lat": 40.7, "lon": 28.3, "sog": sog, "cog": 90.0,
                    "nav_status": 0, "ts": "2026-09-03T09:00:00Z", "name": "Y"}])
    stopped = [{"mmsi": 222, "lat": 40.7, "lon": 28.3, "sog": 0.1, "cog": 90.0,
                "nav_status": 0, "ts": "2026-09-03T09:05:00Z", "name": "Y"}]
    vs.update(stopped)          # now track tail is ... 10.2, 0.1  -> need 2 slow samples
    vs.update(stopped)
    out = detect(vs, stopped, cfg, {"222"})
    assert any(a.kind == "speed-drop" for a in out)


def test_no_flag_when_anchored(tmp_path, cfg):
    vs = _state(tmp_path)
    for sog in (8.0, 7.0):
        vs.update([{"mmsi": 333, "lat": 40.7, "lon": 28.3, "sog": sog, "cog": 90.0,
                    "nav_status": 0, "ts": "2026-09-03T09:00:00Z"}])
    anchored = [{"mmsi": 333, "lat": 40.7, "lon": 28.3, "sog": 0.0, "cog": 0.0,
                 "nav_status": 1, "ts": "2026-09-03T09:05:00Z"}]  # 1 = at anchor
    vs.update(anchored)
    vs.update(anchored)
    out = detect(vs, anchored, cfg, {"333"})
    assert not any(a.kind == "speed-drop" for a in out)


def test_ais_gap(tmp_path, cfg):
    vs = _state(tmp_path)
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))  # 60 min ago
    for _ in range(3):
        vs.update([{"mmsi": 444, "lat": 42.0, "lon": 30.0, "sog": 9.0, "cog": 45.0,
                    "nav_status": 0, "ts": old}])
    out = detect(vs, [], cfg, set())          # 444 not seen this cycle
    assert any(a.kind == "ais-gap" and a.mmsi == 444 for a in out)


def test_gap_ignores_vessel_seen_now(tmp_path, cfg):
    vs = _state(tmp_path)
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
    for _ in range(3):
        vs.update([{"mmsi": 555, "lat": 42.0, "lon": 30.0, "sog": 9.0, "cog": 45.0,
                    "nav_status": 0, "ts": old}])
    out = detect(vs, [], cfg, {"555"})
    assert not any(a.kind == "ais-gap" for a in out)
