"""Tests for Cyber Security Hardening, RFC 7946 GeoJSON Exporter, and Leeway SAR Drift."""

from __future__ import annotations

import json
from pathlib import Path

from run import _is_safe_webhook_url
from src.model import Incident, IncidentType, Severity, Status, Vessel, WeatherContext
from src.process.anomaly import VesselState, is_valid_coord, is_valid_kinematics
from src.process.sar_drift import (
    calculate_leeway_drift,
    enrich_sar_drift,
    predict_sar_drift_trajectory,
)
from src.render.geojson import build_geojson, build_incidents_geojson, build_vessels_geojson
from src.store import Store


def test_ssrf_webhook_url_validation():
    """Verify SSRF protection blocks cloud metadata, link-local IPs, and invalid schemes."""
    # Cloud metadata attacks
    assert not _is_safe_webhook_url("http://169.254.169.254/latest/meta-data/")
    assert not _is_safe_webhook_url("http://169.254.170.2/v2/credentials")
    assert not _is_safe_webhook_url("http://metadata.google.internal/computeMetadata/v1/")
    assert not _is_safe_webhook_url("http://100.100.100.200/latest/meta-data/")

    # Link-local / multicast
    assert not _is_safe_webhook_url("http://169.254.1.1:8080/hook")
    assert not _is_safe_webhook_url("http://224.0.0.1:8080/")

    # Malicious schemes
    assert not _is_safe_webhook_url("ftp://example.com/alert")
    assert not _is_safe_webhook_url("file:///etc/passwd")
    assert not _is_safe_webhook_url("gopher://127.0.0.1:6379/")
    assert not _is_safe_webhook_url("")
    assert not _is_safe_webhook_url(None)

    # Legitimate destinations
    assert _is_safe_webhook_url("http://127.0.0.1:8088/webhook/alert")
    assert _is_safe_webhook_url("http://localhost:8088/webhook/alert")
    assert _is_safe_webhook_url("https://alert.maritimewatch.org/v1/webhook")


def test_ais_coordinate_bounds_and_null_island():
    """Verify coordinate bounds filtering."""
    assert is_valid_coord(41.0082, 28.9784)
    assert is_valid_coord(-34.5, 150.2)

    # Null Island
    assert not is_valid_coord(0.0, 0.0)
    assert not is_valid_coord(0.00001, -0.00001)

    # Out of latitude/longitude ranges
    assert not is_valid_coord(91.0, 28.0)
    assert not is_valid_coord(-95.0, 28.0)
    assert not is_valid_coord(41.0, 185.0)
    assert not is_valid_coord(41.0, -190.0)

    # Non-numeric
    assert not is_valid_coord("bad", None)


def test_ais_kinematic_teleportation_filter():
    """Verify impossible speed spikes (> 80 kn) are rejected from vessel tracks."""
    pt1 = {"lat": 41.0000, "lon": 29.0000, "ts": "2026-09-22T12:00:00Z"}

    # Normal transit: 2 nautical miles in 10 minutes (~12 knots)
    pt2_normal = {"lat": 41.0333, "lon": 29.0000, "ts": "2026-09-22T12:10:00Z"}
    assert is_valid_kinematics(pt1, pt2_normal)

    # Teleportation glitch: 100 nautical miles in 10 minutes (600 knots)
    pt2_teleport = {"lat": 42.6666, "lon": 29.0000, "ts": "2026-09-22T12:10:00Z"}
    assert not is_valid_kinematics(pt1, pt2_teleport)

    # VesselState rejects teleportation
    vs = VesselState(":memory:", history=10)
    # 1st point
    vs.update([{"mmsi": 271000001, "lat": 41.0, "lon": 29.0, "ts": "2026-09-22T12:00:00Z"}])
    assert len(vs.data["271000001"]["track"]) == 1

    # Corrupted / spoofed jump
    vs.update([{"mmsi": 271000001, "lat": 45.0, "lon": 35.0, "ts": "2026-09-22T12:05:00Z"}])
    # Track point should NOT be appended
    assert len(vs.data["271000001"]["track"]) == 1


def test_sar_leeway_drift_calculation():
    """Verify IMO IAMSAR leeway drift mathematics."""
    # North wind (0 deg): downwind drift should head South (180 deg)
    res = calculate_leeway_drift(
        lat=41.0,
        lon=29.0,
        wind_kn=20.0,
        wind_dir_from=0.0,
        current_kn=0.0,
        current_dir_to=0.0,
        hours=2.0,
        target_type="person_in_water",
    )
    assert res["drift_bearing_deg"] == 180.0
    # Leeway factor 0.02 * 20 kn = 0.4 kn * 2h = 0.8 NM
    assert 0.75 <= res["drift_distance_nm"] <= 0.85
    # Latitude should have decreased (moved South)
    assert res["lat"] < 41.0
    # Search radius should have expanded
    assert res["search_radius_nm"] > 0.5

    # Multi-step trajectory prediction
    traj = predict_sar_drift_trajectory(
        lat=40.5,
        lon=28.0,
        wind_kn=25.0,
        wind_dir_from=45.0,
        current_kn=1.2,
        current_dir_to=225.0,
        intervals=(1.0, 3.0, 6.0),
    )
    assert len(traj["projections"]) == 3
    assert traj["projections"][0]["hours"] == 1.0
    assert traj["projections"][2]["hours"] == 6.0
    assert traj["projections"][2]["drift_distance_nm"] > traj["projections"][0]["drift_distance_nm"]


def test_sar_drift_enrichment_on_incident():
    """Verify SAR drift is enriched for man-overboard, distress, and capsize incidents."""
    inc = Incident(
        id="mob-test-1",
        type="man-overboard",
        status=Status.CONFIRMED.value,
        lat=41.1,
        lon=29.1,
        weather_context=WeatherContext(
            wind_kn=18.0,
            gust_kn=24.0,
            wave_m=1.2,
            wind_dir=315,
            beaufort=5,
            summary_tr="test",
            summary_en="test",
        ),
    )
    enrich_sar_drift(inc)
    assert inc.sar_drift is not None
    assert "projections" in inc.sar_drift
    assert len(inc.sar_drift["projections"]) == 3


def test_rfc7946_geojson_generation(tmp_path: Path):
    """Verify GeoJSON exporter outputs valid RFC 7946 FeatureCollections."""
    store = Store(str(tmp_path / "web" / "data"), log_dir=str(tmp_path / "data"))

    inc1 = Incident(
        id="inc-geo-1",
        type=IncidentType.GROUNDING.value,
        status=Status.CONFIRMED.value,
        severity=Severity.MAJOR.value,
        lat=41.1234,
        lon=29.5678,
        area="İstanbul Boğazı",
        vessel=Vessel(name="CARGO SHIP", mmsi=271999999),
        track=[[41.1000, 29.5500], [41.1234, 29.5678]],
    )
    store.upsert_incident(inc1)

    vessels_data = {
        "271888888": {
            "name": "TEST TANKER",
            "type_code": 80,
            "draught": 11.2,
            "length": 220.0,
            "width": 32.0,
            "destination": "TUAPSE",
            "eta": "09-25",
            "track": [
                {"lat": 40.8500, "lon": 28.9000, "sog": 11.4, "cog": 65.0, "nav": 0, "ts": "2026-09-22T12:00:00Z"}
            ],
            "last_seen": "2026-09-22T12:00:00Z",
        }
    }

    out_dir = tmp_path / "web_data"
    build_geojson(store, str(out_dir), vessels_data=vessels_data)

    inc_file = out_dir / "incidents.geojson"
    ves_file = out_dir / "vessels.geojson"

    assert inc_file.exists()
    assert ves_file.exists()

    inc_data = json.loads(inc_file.read_text("utf-8"))
    assert inc_data["type"] == "FeatureCollection"
    # Point feature + LineString track feature
    assert len(inc_data["features"]) == 2

    point_feat = next(f for f in inc_data["features"] if f["geometry"]["type"] == "Point")
    # RFC 7946 specifies [lon, lat]
    assert point_feat["geometry"]["coordinates"] == [29.5678, 41.1234]
    assert point_feat["properties"]["vessel_name"] == "CARGO SHIP"

    ves_data = json.loads(ves_file.read_text("utf-8"))
    assert ves_data["type"] == "FeatureCollection"
    assert len(ves_data["features"]) == 1
    vfeat = ves_data["features"][0]
    assert vfeat["geometry"]["coordinates"] == [28.9000, 40.8500]
    assert vfeat["properties"]["category"] == "tanker"
    assert vfeat["properties"]["draught"] == 11.2

    # Direct dictionary builders
    direct_inc = build_incidents_geojson(store)
    assert len(direct_inc["features"]) == 2
    direct_ves = build_vessels_geojson(vessels_data)
    assert len(direct_ves["features"]) == 1
