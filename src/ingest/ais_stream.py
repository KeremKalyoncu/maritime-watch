"""AIS ingest from aisstream.io.

One short capture per cycle: connect, read positions for `capture_seconds`, close,
return a list of position dicts. Without an API key (or without `websockets`, or on
any error) it falls back to the bundled sample so the rest still runs offline.

aisstream.io sends decoded JSON already, so no NMEA parsing here. Nav-status codes
are ITU-R M.1371 (2 = not under command, 6 = aground).
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

try:
    import websockets
except ImportError:
    websockets = None

SAMPLE = Path(__file__).parent / "samples" / "ais_sample.json"


def _load_sample() -> list[dict]:
    if SAMPLE.exists():
        return json.loads(SAMPLE.read_text("utf-8"))
    return []


async def _capture(key: str, bbox: dict, url: str, seconds: int) -> list[dict]:
    sub = {
        "APIKey": key,
        "BoundingBoxes": [[[bbox["lat_min"], bbox["lon_min"]], [bbox["lat_max"], bbox["lon_max"]]]],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData", "SafetyBroadcastMessage"],
    }
    positions: list[dict] = []
    static: dict = {}
    deadline = time.time() + seconds

    async with websockets.connect(url, ping_interval=20, close_timeout=5, max_size=2 ** 20) as ws:
        await ws.send(json.dumps(sub))
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
            except Exception:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("MessageType")
            meta = msg.get("MetaData", {})
            mmsi = meta.get("MMSI") or meta.get("MMSI_String")

            if mtype == "ShipStaticData":
                d = msg.get("Message", {}).get("ShipStaticData", {})
                static[mmsi] = {
                    "name": (d.get("Name") or "").strip(),
                    "type_code": d.get("Type"),
                    "callsign": (d.get("CallSign") or "").strip(),
                }
            elif mtype == "PositionReport":
                d = msg.get("Message", {}).get("PositionReport", {})
                positions.append({
                    "mmsi": mmsi,
                    "lat": d.get("Latitude"),
                    "lon": d.get("Longitude"),
                    "sog": d.get("Sog"),
                    "cog": d.get("Cog"),
                    "true_heading": d.get("TrueHeading"),
                    "nav_status": d.get("NavigationalStatus"),
                    "ts": meta.get("time_utc") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "name": (meta.get("ShipName") or "").strip(),
                })
            elif mtype == "SafetyBroadcastMessage":
                d = msg.get("Message", {}).get("SafetyBroadcastMessage", {})
                positions.append({
                    "msg_type": "safety",
                    "mmsi": mmsi,
                    "lat": meta.get("latitude"),
                    "lon": meta.get("longitude"),
                    "text": (d.get("Text") or "").strip(),
                    "ts": meta.get("time_utc") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "name": (meta.get("ShipName") or "").strip(),
                })

    for p in positions:
        s = static.get(p["mmsi"])
        if s:
            p["name"] = p["name"] or s["name"]
            p["type_code"] = s["type_code"]
            p["callsign"] = s["callsign"]
    return positions


def capture_ais(cfg: dict) -> list[dict]:
    key = cfg["secrets"]["aisstream_key"]
    ais = cfg["ais"]
    if not ais.get("enabled", True) or not key or websockets is None:
        if not key:
            print("[ais] no AISSTREAM_KEY -> using bundled sample")
        elif websockets is None:
            print("[ais] 'websockets' not installed -> using bundled sample")
        return _load_sample()
    try:
        out = asyncio.run(_capture(key, cfg["region"]["bbox"], ais["ws_url"], ais["capture_seconds"]))
        return out or _load_sample()
    except Exception as e:
        print(f"[ais] capture failed ({e}) -> using bundled sample")
        return _load_sample()
