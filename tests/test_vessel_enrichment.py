"""Unit tests for enriched vessel telemetry, hazardous cargo classification,
grounding risk, and Turkish Straits risk intelligence.
"""

from __future__ import annotations

import pytest

from src.model import StraitStatus, Vessel
from src.process.anomaly import VesselState, detect
from src.process.shallow_banks import evaluate_grounding_risk
from src.process.shiptype import (
    hazard_category,
    is_dangerous_cargo,
    is_large_vessel,
)
from src.render.straits import evaluate_strait


class TestVesselModelAndSerialization:
    def test_vessel_defaults_and_fields(self):
        v = Vessel(
            name="ISTANBUL STAR",
            mmsi=271099888,
            draught=14.5,
            length=274.0,
            width=48.0,
            destination="ALIAGA",
            eta="10-15 08:30",
            rot=-25.4,
            cargo_hazard="crude_oil",
            is_large_vessel=True,
        )
        assert v.draught == 14.5
        assert v.length == 274.0
        assert v.is_large_vessel is True
        assert v.cargo_hazard == "crude_oil"

        d = v.to_dict()
        assert d["draught"] == 14.5
        assert d["is_large_vessel"] is True
        assert d["rot"] == -25.4

        # Roundtrip from_dict
        v2 = Vessel.from_dict(d)
        assert v2.name == "ISTANBUL STAR"
        assert v2.length == 274.0
        assert v2.is_large_vessel is True

    def test_vessel_from_dict_handles_unknown_fields_gracefully(self):
        legacy_data = {
            "name": "OLD VESSEL",
            "mmsi": 271000111,
            "some_obsolete_key": "ignore_me",
        }
        v = Vessel.from_dict(legacy_data)
        assert v.name == "OLD VESSEL"
        assert v.draught is None
        assert v.is_large_vessel is False


class TestHazardAndDimensionsClassification:
    @pytest.mark.parametrize(
        "type_code, name, expected",
        [
            (84, "GAS PIONEER", "lng_lpg"),
            (82, "CHEM TRANSPORTER", "chemical"),
            (81, "BALTIC CRUDE", "crude_oil"),
            (83, "AEGEAN TANKER", "crude_oil"),
            (80, "GENERIC TANKER", "crude_oil"),
            (71, "CONTAINER DG A", "dangerous_goods"),
            (74, "BULK HAZMAT", "dangerous_goods"),
            (70, "DRY BULK CARRIER", "none"),
            (30, "BALIKCI AHMET", "none"),
            (None, "UNKNOWN SHIP", "none"),
            (None, "PACIFIC LNG TANKER", "lng_lpg"),
            (70, "CLEAN LPG CARRIER", "lng_lpg"),
        ],
    )
    def test_hazard_category_classification(self, type_code, name, expected):
        assert hazard_category(type_code, name) == expected

    def test_is_dangerous_cargo(self):
        assert is_dangerous_cargo(84) is True
        assert is_dangerous_cargo(82) is True
        assert is_dangerous_cargo(70) is False
        assert is_dangerous_cargo(30) is False
        assert is_dangerous_cargo(None, "OCEAN GAS CARRIER") is True

    @pytest.mark.parametrize(
        "length, expected",
        [
            (200.0, True),
            (299.5, True),
            (199.9, False),
            (45.0, False),
            (0.0, False),
            (None, False),
            ("250", True),
            ("invalid", False),
        ],
    )
    def test_is_large_vessel(self, length, expected):
        assert is_large_vessel(length) == expected


class TestGroundingRiskAnalysis:
    def test_deep_draught_vessel_near_kumkapi_shoal(self):
        # Kumkapi shoal is at lat=41.0000, lon=28.9650, depth=6.0m, radius=0.45 NM
        # Vessel has 12.5m draught and is 0.1 NM away
        res = evaluate_grounding_risk(
            lat=41.0010,
            lon=28.9660,
            draught=12.5,
            sog=8.5,
        )
        assert res is not None
        assert res["bank_id"] == "kumkapi"
        assert res["bank_depth_m"] == 6.0
        assert res["vessel_draught_m"] == 12.5
        assert res["under_keel_clearance_m"] < 0  # Negative clearance = grounding!
        assert res["distance_nm"] < 0.45

    def test_shallow_draught_vessel_is_safe(self):
        # Same location, but small vessel draught (3.0m)
        res = evaluate_grounding_risk(
            lat=41.0010,
            lon=28.9660,
            draught=3.0,
            sog=8.5,
        )
        assert res is None

    def test_deep_draught_vessel_far_away_is_safe(self):
        # 14m draught but 5 NM away in deep Marmara water
        res = evaluate_grounding_risk(
            lat=40.8500,
            lon=28.8000,
            draught=14.0,
            sog=12.0,
        )
        assert res is None

    def test_grounding_risk_null_tolerance(self):
        assert evaluate_grounding_risk(None, 28.96, 12.0) is None
        assert evaluate_grounding_risk(41.00, None, 12.0) is None
        assert evaluate_grounding_risk(41.00, 28.96, None) is None


class TestRotSpikeAnomaly:
    @pytest.fixture
    def cfg(self):
        return {
            "anomaly": {
                "moving_speed_kn": 4.0,
                "stopped_speed_kn": 1.0,
                "gap_minutes": 20,
            },
            "region": {"bbox": {"lat_min": 35.0, "lat_max": 43.0, "lon_min": 25.0, "lon_max": 42.0}},
            "ais": {"distress_mmsi_prefixes": ("970", "972", "974")},
        }

    def test_rot_spike_detected_underway(self, cfg, tmp_path):
        vs = VesselState(str(tmp_path / "vessels.json"), 10)
        positions = [
            {
                "mmsi": 271001234,
                "lat": 41.0850,
                "lon": 29.0520,
                "sog": 9.5,
                "cog": 45.0,
                "nav_status": 0,
                "rot": 28.5,  # 28.5 deg/min extreme turn
                "name": "BOSPHORUS TANKER",
                "ts": "2026-09-22T12:00:00Z",
            }
        ]
        vs.update(positions)
        anomalies = detect(vs, positions, cfg, seen_now={"271001234"})
        rot_anomalies = [a for a in anomalies if a.kind == "rot-spike"]
        assert len(rot_anomalies) == 1
        assert "ani ve aşırı dönüş" in rot_anomalies[0].detail
        assert rot_anomalies[0].severity in ("major", "critical")

    def test_rot_spike_ignored_when_anchored(self, cfg, tmp_path):
        vs = VesselState(str(tmp_path / "vessels.json"), 10)
        positions = [
            {
                "mmsi": 271001234,
                "lat": 41.0850,
                "lon": 29.0520,
                "sog": 0.2,
                "cog": 45.0,
                "nav_status": 1,  # Anchored swinging on chain
                "rot": 35.0,
                "name": "ANCHORED SHIP",
                "ts": "2026-09-22T12:00:00Z",
            }
        ]
        vs.update(positions)
        anomalies = detect(vs, positions, cfg, seen_now={"271001234"})
        rot_anomalies = [a for a in anomalies if a.kind == "rot-spike"]
        assert len(rot_anomalies) == 0


class TestStraitTrafficIntelligence:
    def test_evaluate_strait_counts_deep_draft_large_and_hazmat(self):
        vessels = {
            "2710001": {
                "name": "MEGA TANKER",
                "type_code": 81,  # crude oil
                "length": 250.0,  # large vessel
                "draught": 13.8,  # deep draft
                "track": [{"lat": 41.10, "lon": 29.05, "sog": 8.0, "ts": "2026-09-22T12:00:00Z"}],
            },
            "2710002": {
                "name": "CONTAINER SHIP",
                "type_code": 70,
                "length": 220.0,  # large vessel
                "draught": 9.5,  # normal draft
                "track": [{"lat": 41.12, "lon": 29.06, "sog": 9.2, "ts": "2026-09-22T12:00:00Z"}],
            },
            "2710003": {
                "name": "COASTAL TUG",
                "type_code": 52,
                "length": 35.0,
                "draught": 4.2,
                "track": [{"lat": 41.15, "lon": 29.07, "sog": 5.0, "ts": "2026-09-22T12:00:00Z"}],
            },
        }
        res = evaluate_strait("bosphorus", warnings=[], vessels_data=vessels)
        assert isinstance(res, StraitStatus)
        assert res.active_vessels_in_transit == 3
        assert res.large_vessel_count == 2
        assert res.deep_draft_count == 1
        assert res.hazmat_tanker_count == 1
