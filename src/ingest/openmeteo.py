"""Marine + wind forecast from Open-Meteo (free, no API key).

For each configured point we look at the next `hours_ahead` hours and raise a
Warning if the significant wave height or the wind gust crosses the threshold.
This is the reliable replacement for the MGM scrape.
"""

from __future__ import annotations

from ..model import Warning, now_iso
from ._net import get_json

MARINE = "https://marine-api.open-meteo.com/v1/marine"
WIND = "https://api.open-meteo.com/v1/forecast"


def _series(url: str, params: dict, sample: str, field: str):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    data, live = get_json(f"{url}?{q}", sample)
    if not data:
        return [], live
    vals = (data.get("hourly") or {}).get(field) or []
    return [v for v in vals if isinstance(v, (int, float))], live


def fetch_marine_warnings(cfg: dict) -> list[Warning]:
    om = cfg["openmeteo"]
    hours = int(om["hours_ahead"])
    out: list[Warning] = []

    for pt in om["points"]:
        name, lat, lon = pt["name"], pt["lat"], pt["lon"]
        waves, live1 = _series(MARINE, {
            "latitude": lat, "longitude": lon,
            "hourly": "wave_height", "forecast_days": 2,
        }, "openmeteo_marine.json", "wave_height")
        gusts, live2 = _series(WIND, {
            "latitude": lat, "longitude": lon,
            "hourly": "wind_gusts_10m", "wind_speed_unit": "kn", "forecast_days": 2,
        }, "openmeteo_wind.json", "wind_gusts_10m")

        max_wave = max(waves[:hours]) if waves else 0.0
        max_gust = max(gusts[:hours]) if gusts else 0.0

        if max_wave >= om["wave_m"] or max_gust >= om["wind_gust_kn"]:
            bits = []
            if max_wave:
                bits.append(f"dalga ~{max_wave:.1f} m")
            if max_gust:
                bits.append(f"rüzgar hamlesi ~{max_gust:.0f} kn")
            strong = max_wave >= om["wave_m"] + 1.0 or max_gust >= om["wind_gust_kn"] + 10
            out.append(Warning(
                id=f"om-{name.lower().replace(' ', '')[:18]}-{now_iso()[:13]}",
                headline=f"{name}: {', '.join(bits)} (önümüzdeki {hours} saat)",
                area=name,
                kind="marine-weather",
                severity="major" if strong else "minor",
                org="Open-Meteo",
                url="https://open-meteo.com/en/docs/marine-weather-api",
                issued=now_iso(),
                value=round(max_wave, 1) or None,
                lat=lat, lon=lon,
            ))

        # offline: the sample is the same for every point, so stop after one
        if not (live1 and live2):
            break

    return out
