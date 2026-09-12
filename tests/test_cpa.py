import math
from src.process.cpa import (
    calculate_cpa,
    cpa_events_to_incidents,
    detect_cpa_risks,
    is_vessel_underway,
)


def test_tc_cpa_01_head_on_collision_risk():
    # Vessel 1: heading North (0 deg), at lat 40.00, lon 28.00, SOG 15 kn
    # Vessel 2: heading South (180 deg), at lat 40.02, lon 28.0005, SOG 15 kn
    # Distance is ~1.2 NM, closing speed is 30 kn
    p1 = {"mmsi": 271001, "name": "Vessel Alpha", "lat": 40.00, "lon": 28.00, "sog": 15.0, "cog": 0.0}
    p2 = {"mmsi": 271002, "name": "Vessel Beta", "lat": 40.02, "lon": 28.0005, "sog": 15.0, "cog": 180.0}

    res = calculate_cpa(p1, p2)
    assert res is not None
    cpa_nm, tcpa_min = res
    assert cpa_nm < 0.1  # very close passage
    assert 0 < tcpa_min < 5.0  # within a few minutes

    events = detect_cpa_risks([p1, p2])
    assert len(events) == 1
    assert events[0].mmsi1 == 271001
    assert events[0].mmsi2 == 271002
    assert events[0].cpa_nm < 0.35
    assert events[0].tcpa_min <= 12.0


def test_tc_cpa_02_crossing_collision_risk():
    # Vessel 1: Eastbound (90 deg), at lat 40.00, lon 28.00, SOG 12 kn
    # Vessel 2: Northbound (0 deg), at lat 39.98, lon 28.02, SOG 12 kn
    p1 = {"mmsi": 271010, "lat": 40.00, "lon": 28.00, "sog": 12.0, "cog": 90.0}
    p2 = {"mmsi": 271020, "lat": 39.98, "lon": 28.02, "sog": 12.0, "cog": 0.0}

    res = calculate_cpa(p1, p2)
    assert res is not None
    cpa_nm, tcpa_min = res
    assert cpa_nm < 0.35
    assert 0 < tcpa_min <= 12.0


def test_tc_cpa_03_diverging_vessels():
    # Vessels have already crossed and are moving away from each other
    p1 = {"mmsi": 271030, "lat": 40.05, "lon": 28.00, "sog": 15.0, "cog": 0.0}
    p2 = {"mmsi": 271040, "lat": 39.95, "lon": 28.00, "sog": 15.0, "cog": 180.0}

    res = calculate_cpa(p1, p2)
    # Diverging vessels should return None
    assert res is None
    assert detect_cpa_risks([p1, p2]) == []


def test_tc_cpa_04_safe_distance_crossing():
    # Crossing but safe clearance > 0.35 NM
    # Vessel 1: at lon 28.00, Vessel 2: at lon 28.05 (~2.3 NM offset)
    p1 = {"mmsi": 271050, "lat": 40.00, "lon": 28.00, "sog": 12.0, "cog": 0.0}
    p2 = {"mmsi": 271060, "lat": 40.00, "lon": 28.05, "sog": 12.0, "cog": 0.0}

    # Parallel course, relative velocity is zero -> calculate_cpa returns None
    assert calculate_cpa(p1, p2) is None


def test_tc_cpa_05_coarse_distance_filter():
    # Distance > 3 NM (e.g. 10 NM away)
    p1 = {"mmsi": 271070, "lat": 40.00, "lon": 28.00, "sog": 15.0, "cog": 0.0}
    p2 = {"mmsi": 271080, "lat": 40.30, "lon": 28.00, "sog": 15.0, "cog": 180.0}

    res = calculate_cpa(p1, p2)
    assert res is None


def test_tc_cpa_06_anchored_vessel_filter():
    # One vessel is anchored (nav_status = 1) or stopped (SOG < 3.0 kn)
    p_anchored = {"mmsi": 271090, "lat": 40.00, "lon": 28.00, "sog": 0.3, "cog": 0.0, "nav_status": 1}
    p_moving = {"mmsi": 271091, "lat": 40.01, "lon": 28.00, "sog": 12.0, "cog": 180.0}

    assert not is_vessel_underway(p_anchored)
    assert is_vessel_underway(p_moving)
    assert detect_cpa_risks([p_anchored, p_moving]) == []


def test_tc_cpa_07_identical_course_and_speed_zero_relative_velocity():
    # Same speed, same heading -> v_rel = 0
    p1 = {"mmsi": 271101, "lat": 40.00, "lon": 28.00, "sog": 14.0, "cog": 45.0}
    p2 = {"mmsi": 271102, "lat": 40.01, "lon": 28.01, "sog": 14.0, "cog": 45.0}

    res = calculate_cpa(p1, p2)
    assert res is None


def test_tc_cpa_08_incident_conversion_idempotency():
    p1 = {"mmsi": 271200, "name": "Cargo 1", "lat": 40.00, "lon": 28.00, "sog": 15.0, "cog": 0.0}
    p2 = {"mmsi": 271100, "name": "Tanker 2", "lat": 40.02, "lon": 28.0005, "sog": 15.0, "cog": 180.0}

    events = detect_cpa_risks([p1, p2])
    assert len(events) == 1

    incidents = cpa_events_to_incidents(events)
    assert len(incidents) == 1
    inc = incidents[0]

    # Deterministic ID based on min and max MMSI
    assert inc.id == "cpa-271100-271200"
    assert inc.type == "collision-risk"
    assert inc.severity == "major"
    assert "cpa" in inc.sources[0].kind
