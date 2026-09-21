from __future__ import annotations

from unittest.mock import patch

from src.ingest.openmeteo import fetch_forecast_points, reset_cache
from src.process.cpa import calculate_cpa, is_vessel_underway


def test_openmeteo_null_sst_and_current_graceful():
    # Open-Meteo deniz suyu sıcaklığı veya akıntı verisi null döndüğünde sistem çökmemeli
    reset_cache()
    cfg = {
        "openmeteo": {
            "hours_ahead": 12,
            "points": [
                {"name": "Marmara Denizi", "lat": 40.8, "lon": 28.5},
            ],
        },
    }

    dummy_marine_null = {
        "hourly": {
            "time": ["2026-09-18T14:00", "2026-09-18T15:00"],
            "wave_height": [0.6, 0.7],
            "sea_surface_temperature": [None, None],
            "ocean_current_velocity": [None, None],
        }
    }
    dummy_wind = {
        "hourly": {
            "time": ["2026-09-18T14:00", "2026-09-18T15:00"],
            "wind_gusts_10m": [14.0, 16.0],
        }
    }

    def fake_get_json(url, sample):
        if "marine" in url:
            return dummy_marine_null, True
        return dummy_wind, True

    with patch("src.ingest.openmeteo.get_json", side_effect=fake_get_json):
        pts = fetch_forecast_points(cfg)

    assert len(pts) == 1
    p = pts[0]
    assert p["name"] == "Marmara Denizi"
    assert p["sea_temp_c"] is None
    assert p["current_kn"] is None
    assert len(p["waves"]) >= 1
    assert len(p["gusts"]) >= 1
    reset_cache()


def test_cpa_edge_cases():
    # 1. Demirlemiş veya bağlı gemiler (nav_status=1 veya 5, ya da sog < 3.0) seyirde sayılmaz
    anchored = {"nav_status": 1, "sog": 0.1, "lat": 40.9, "lon": 28.9}
    slow = {"nav_status": 0, "sog": 1.2, "lat": 40.9, "lon": 28.9}
    underway = {"nav_status": 0, "sog": 12.0, "lat": 40.9, "lon": 28.9}

    assert not is_vessel_underway(anchored)
    assert not is_vessel_underway(slow)
    assert is_vessel_underway(underway)

    # 2. Birbirinden uzaklaşan gemiler (TCPA <= 0) çatışma riski oluşturmaz
    p1 = {"lat": 41.00, "lon": 29.00, "sog": 10.0, "cog": 0.0}  # Kuzeye gidiyor
    p2 = {"lat": 40.95, "lon": 29.00, "sog": 10.0, "cog": 180.0}  # Güneye gidiyor (uzaklaşıyorlar)
    res = calculate_cpa(p1, p2)
    assert res is None

    # 3. Aynı hız ve aynı rotadaki gemiler (paralel seyir)
    p3 = {"lat": 41.00, "lon": 29.00, "sog": 12.0, "cog": 90.0}
    p4 = {"lat": 41.01, "lon": 29.00, "sog": 12.0, "cog": 90.0}
    res_parallel = calculate_cpa(p3, p4)
    assert res_parallel is None
