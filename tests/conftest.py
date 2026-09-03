import pytest


@pytest.fixture
def cfg(tmp_path):
    return {
        "_root": str(tmp_path),
        "site": {"url": "https://example.github.io/maritime-watch", "repo": "https://github.com/x/y"},
        "region": {"name": "Türkiye", "bbox": {"lat_min": 35.0, "lat_max": 43.5, "lon_min": 25.0, "lon_max": 42.5}},
        "ais": {
            "enabled": True, "ws_url": "wss://x", "capture_seconds": 1, "vessel_history": 20,
            "distress_mmsi_prefixes": ["970", "972", "974"],
        },
        "anomaly": {
            "moving_speed_kn": 3.0, "stopped_speed_kn": 0.5, "stop_minutes": 20,
            "gap_minutes": 45, "course_change_deg": 60,
        },
        "sources": {"scrape": True, "openmeteo": True, "quakes": True, "navwarn": True,
                    "news": True, "gdacs": True, "eonet": True, "reliefweb": True, "metar": True},
        "scrape": {
            "mgm": True, "sahil_guvenlik": True, "afad": True,
            "keywords": ["kaza", "batık", "alabora", "kurtar", "mahsur", "sürüklen", "tekne", "kayıp"],
        },
        "openmeteo": {
            "wave_m": 2.0, "wind_gust_kn": 33.0, "hours_ahead": 36,
            "points": [{"name": "Marmara Denizi", "lat": 40.75, "lon": 28.30}],
        },
        "quakes": {"min_mag": 3.8, "hours_back": 24},
        "navwarn": {"keep_terms": ["turkey", "marmara", "aegean", "black sea", "bosphorus"]},
        "news": {
            "max_items_per_feed": 40, "hours_back": 36,
            "feeds": ["https://a.example/rss", "https://b.example/rss"],
            "maritime_words": ["deniz", "tekne", "gemi", "balıkçı", "açıklar", "boğaz"],
            "incident_words": ["battı", "batan", "alabora", "kurtar", "kayıp", "mahsur", "fırtına", "göçmen"],
        },
        "gdacs": {"alert_levels": ["Orange", "Red"], "event_types": ["TC", "FL", "EQ", "WF"]},
        "metar": {"stations": ["LTBA", "LTFE", "LTAI"], "wind_gust_kn": 33.0, "visibility_m": 2000},
        "alert": {"telegram": {"enabled": True, "only_status": ["confirmed", "probable"],
                               "prevention": True, "send_location_pin": True},
                  "min_severity": "major"},
        "loop": {"interval_seconds": 900},
        "secrets": {"aisstream_key": "", "telegram_token": "", "telegram_chat_id": ""},
    }
