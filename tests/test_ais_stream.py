from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from src.ingest.ais_stream import _capture, capture_ais


def test_ais_offline_sample_fallback():
    # API anahtarı boş olduğunda sistem çökmeden yerel örneği döner
    cfg = {
        "secrets": {"aisstream_key": ""},
        "ais": {"enabled": True, "ws_url": "wss://stream.aisstream.io/v0/stream", "capture_seconds": 1},
        "region": {"bbox": {"lat_min": 40.0, "lat_max": 41.5, "lon_min": 26.0, "lon_max": 30.0}},
    }
    sample = capture_ais(cfg)
    assert isinstance(sample, list)
    assert len(sample) > 0
    assert any("mmsi" in item for item in sample)


def test_ais_capture_corrupt_json_and_merge():
    # WebSocket üzerinden bozuk JSON geldiğinde döngünün çökmemesini ve static veri birleştirmesini test eder
    msg_static = json.dumps(
        {
            "MessageType": "ShipStaticData",
            "MetaData": {
                "MMSI": 271000111,
                "ShipName": "ISTANBUL FERIBOT",
                "time_utc": "2026-09-18T14:00:00Z",
            },
            "Message": {
                "ShipStaticData": {
                    "Name": "ISTANBUL FERIBOT",
                    "Type": 60,
                    "CallSign": "TC9988",
                }
            },
        }
    )
    msg_bad = "{corrupt-invalid-json-content"
    msg_pos = json.dumps(
        {
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 271000111,
                "ShipName": "ISTANBUL FERIBOT",
                "time_utc": "2026-09-18T14:00:05Z",
            },
            "Message": {
                "PositionReport": {
                    "Latitude": 41.02,
                    "Longitude": 28.98,
                    "Sog": 12.5,
                    "Cog": 180.0,
                    "TrueHeading": 181,
                    "NavigationalStatus": 0,
                }
            },
        }
    )
    msg_safety = json.dumps(
        {
            "MessageType": "SafetyBroadcastMessage",
            "MetaData": {"MMSI": 271000222, "latitude": 40.95, "longitude": 28.85, "ShipName": "RESCUE_01"},
            "Message": {
                "SafetyBroadcastMessage": {
                    "Text": "SECURITE SECURITE BUOY ADRIFT",
                }
            },
        }
    )

    class FakeWS:
        def __init__(self):
            self.frames = [msg_static, msg_bad, msg_pos, msg_safety]
            self.sent = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def send(self, data):
            self.sent.append(data)

        async def recv(self):
            if self.frames:
                return self.frames.pop(0)
            await asyncio.sleep(1.0)
            raise TimeoutError()

    bbox = {"lat_min": 40.0, "lat_max": 41.5, "lon_min": 26.0, "lon_max": 30.0}

    with patch("src.ingest.ais_stream.websockets.connect", return_value=FakeWS()):
        positions = asyncio.run(_capture("test_key", bbox, "wss://dummy", seconds=1))

    assert len(positions) == 2

    # 1. PositionReport doğrulaması (static veriyle birleşmiş olmalı)
    p = positions[0]
    assert p["mmsi"] == 271000111
    assert p["lat"] == 41.02
    assert p["lon"] == 28.98
    assert p["sog"] == 12.5
    assert p["name"] == "ISTANBUL FERIBOT"
    assert p["type_code"] == 60
    assert p["callsign"] == "TC9988"

    # 2. SafetyBroadcast doğrulaması
    s = positions[1]
    assert s["msg_type"] == "safety"
    assert s["mmsi"] == 271000222
    assert "SECURITE" in s["text"]
