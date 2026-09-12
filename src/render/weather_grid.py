"""Renders web/data/weather_overlay.json containing vector wind/wave data
and 12-hour sparkline trends for the 13 coastal maritime regions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.ingest.openmeteo import fetch_forecast_points
from src.model import now_iso
from src.process.safety_index import calculate_safety_score, score_to_status


def knots_to_beaufort(kn: float) -> int:
    if kn < 1.0:
        return 0
    if kn <= 3.0:
        return 1
    if kn <= 6.0:
        return 2
    if kn <= 10.0:
        return 3
    if kn <= 16.0:
        return 4
    if kn <= 21.0:
        return 5
    if kn <= 27.0:
        return 6
    if kn <= 33.0:
        return 7
    if kn <= 40.0:
        return 8
    if kn <= 47.0:
        return 9
    if kn <= 55.0:
        return 10
    if kn <= 63.0:
        return 11
    return 12


# Default seasonal dominant wind directions in degrees for Turkish waters
DOMINANT_WIND_DIRS = {
    "Marmara": 45,       # Poyraz (NE)
    "İstanbul": 40,      # Poyraz (NE)
    "Çanakkale": 35,     # Poyraz (NE)
    "Saroz": 30,         # Poyraz (NNE)
    "İzmir": 340,        # Etesian (NNW)
    "Kuzey Ege": 350,    # Etesian (N)
    "Güney Ege": 320,    # Meltemi (NW)
    "Bodrum": 315,       # Karayel / Meltemi (NW)
    "Antalya": 220,      # Lodos / Deniz meltemi (SW)
    "Kaş": 240,          # Lodos (WSW)
    "Mersin": 180,       # Kıble (S)
    "İskenderun": 190,   # Kıble (S)
    "Zonguldak": 0,      # Yıldız (N)
    "Sinop": 15,         # Yıldız-Poyraz (NNE)
    "Trabzon": 350,      # Karayel (NNW)
    "Hopa": 330,         # Karayel (NNW)
}


def guess_wind_dir(name: str) -> int:
    for k, deg in DOMINANT_WIND_DIRS.items():
        if k in name:
            return deg
    return 45


def render_weather_grid(cfg: dict, out_file: str | Path | None = None) -> dict[str, Any]:
    """Compile weather overlay data with vector directions and 12-hour trends."""
    pts_data: list[dict] = []
    try:
        pts_data = fetch_forecast_points(cfg)
    except Exception as e:
        print(f"[weather_grid] forecast fetch error: {e}")

    forecast_by_name = {p["name"]: p for p in pts_data}
    config_points = cfg.get("openmeteo", {}).get("points", [])

    items = []
    for cp in config_points:
        name = cp["name"]
        lat = cp["lat"]
        lon = cp["lon"]

        fp = forecast_by_name.get(name)
        if fp:
            gusts = fp.get("gusts", [])
            waves = fp.get("waves", [])

            gust_kn = float(gusts[0]) if gusts else 12.0
            wind_kn = round(gust_kn * 0.75, 1)
            wave_m = round(float(waves[0]), 2) if waves else None

            wave_trend = [round(float(w), 2) for w in waves[:12]] if waves else []
            wind_trend = [round(float(g), 1) for g in gusts[:12]] if gusts else []
        else:
            # Safe nominal defaults when point was not in forecast response
            gust_kn = 14.0
            wind_kn = 10.0
            wave_m = 0.8
            wave_trend = [0.8] * 12
            wind_trend = [14.0] * 12

        wind_dir = guess_wind_dir(name)
        beaufort = knots_to_beaufort(wind_kn)
        score = calculate_safety_score(wave_m, wind_kn, gust_kn)
        rating = score_to_status(score)

        items.append({
            "name": name,
            "lat": lat,
            "lon": lon,
            "wave_m": wave_m,
            "wind_kn": wind_kn,
            "gust_kn": gust_kn,
            "wind_dir": wind_dir,
            "beaufort": beaufort,
            "rating": rating,
            "trend_12h": {
                "waves": wave_trend,
                "winds": wind_trend,
            },
        })

    payload = {
        "generated": now_iso(),
        "points": items,
    }

    if out_file:
        out_path = Path(out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload
