import pytest


@pytest.fixture
def cfg(tmp_path):
    return {
        "_root": str(tmp_path),
        "region": {"bbox": {"lat_min": 35.0, "lat_max": 43.5, "lon_min": 25.0, "lon_max": 42.5}},
        "ais": {"enabled": True, "ws_url": "wss://x", "capture_seconds": 1, "vessel_history": 20},
        "anomaly": {
            "moving_speed_kn": 3.0, "stopped_speed_kn": 0.5, "stop_minutes": 20,
            "gap_minutes": 45, "course_change_deg": 60,
        },
        "scrape": {
            "enabled": True, "mgm": True, "sahil_guvenlik": True, "afad": True,
            "keywords": ["kaza", "batık", "alabora", "kurtar", "mahsur", "sürüklen", "tekne", "kayıp"],
        },
        "alert": {"telegram": {"enabled": True, "only_status": ["confirmed"], "prevention": True},
                  "min_severity": "major"},
        "loop": {"interval_seconds": 900},
        "secrets": {"aisstream_key": "", "telegram_token": "", "telegram_chat_id": ""},
    }
