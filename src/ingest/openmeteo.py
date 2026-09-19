"""Marine + wind forecast from Open-Meteo (free, no API key).

For each configured point we look at the next `hours_ahead` hours and raise a
Warning if the significant wave height or the wind gust crosses the threshold.
This is the reliable replacement for the MGM scrape.
"""

from __future__ import annotations

import time

from ..model import Warning, now_iso
from ._net import get_json

MARINE = "https://marine-api.open-meteo.com/v1/marine"
WIND = "https://api.open-meteo.com/v1/forecast"

_FORECAST_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SEC: float = 900.0  # 15 minutes TTL


def reset_cache() -> None:
    _FORECAST_CACHE.clear()


def _series(url: str, params: dict, sample: str, field: str):
    """Hourly values starting at the current hour.

    The API answers from 00:00 UTC of the current day, so slicing the first N
    entries meant the forecast window shrank as the day went on: a run at 23:00
    was looking 13 hours ahead while the message still promised 36, and a gale
    starting the next evening fell outside it.
    """
    q = "&".join(f"{k}={v}" for k, v in params.items())
    data, live = get_json(f"{url}?{q}", sample)
    if not data:
        return [], live
    hourly = data.get("hourly") or {}
    vals = hourly.get(field) or []
    times = hourly.get("time") or []
    start = 0
    if len(times) == len(vals):
        cutoff = time.strftime("%Y-%m-%dT%H:00", time.gmtime())
        start = next((i for i, t in enumerate(times) if str(t) >= cutoff), 0)
    return [v for v in vals[start:] if isinstance(v, (int, float))], live


def _hourly(url: str, params: dict, sample: str, field: str):
    """Like _series but keeps the timestamps: the daily outlook needs to say
    *when*, not just how much. Null API cells stay None (never coerced to 0)."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    data, live = get_json(f"{url}?{q}", sample)
    if not data:
        return [], [], live
    hourly = data.get("hourly") or {}
    vals, times = hourly.get(field) or [], hourly.get("time") or []
    if len(times) != len(vals):
        return [], [], live
    cutoff = time.strftime("%Y-%m-%dT%H:00", time.gmtime())
    start = next((i for i, t in enumerate(times) if str(t) >= cutoff), 0)
    cleaned = [float(v) if isinstance(v, (int, float)) else None for v in vals[start:]]
    return times[start:], cleaned, live


def _hourly_marine(url: str, params: dict, sample: str):
    """Fetch wave height, sea temp and ocean current in a single combined HTTP request."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    data, live = get_json(f"{url}?{q}", sample)
    if not data:
        return [], [], None, None, live
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    waves = hourly.get("wave_height") or []
    sst = hourly.get("sea_surface_temperature") or []
    cur = hourly.get("ocean_current_velocity") or []
    cutoff = time.strftime("%Y-%m-%dT%H:00", time.gmtime())
    start = next((i for i, t in enumerate(times) if str(t) >= cutoff), 0)
    t_sliced = times[start:]
    # Keep index alignment with times — drop-filter would invent calm hours
    w_sliced = [
        float(v) if isinstance(v, (int, float)) else None
        for v in waves[start:start + len(t_sliced)]
    ]
    while len(w_sliced) < len(t_sliced):
        w_sliced.append(None)
    s_val = (
        round(float(sst[start]), 1)
        if (start < len(sst) and sst[start] is not None and isinstance(sst[start], (int, float)))
        else None
    )
    c_val = (
        round(float(cur[start]) * 0.539957, 1)
        if (start < len(cur) and cur[start] is not None and isinstance(cur[start], (int, float)))
        else None
    )
    return t_sliced, w_sliced, s_val, c_val, live


def _hourly_wind(url: str, params: dict, sample: str):
    """Gusts + direction in one request; null cells stay None."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    data, live = get_json(f"{url}?{q}", sample)
    if not data:
        return [], [], [], live
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    gusts = hourly.get("wind_gusts_10m") or []
    dirs = hourly.get("wind_direction_10m") or []
    if len(times) != len(gusts):
        return [], [], [], live
    cutoff = time.strftime("%Y-%m-%dT%H:00", time.gmtime())
    start = next((i for i, t in enumerate(times) if str(t) >= cutoff), 0)
    t_sliced = times[start:]
    g_sliced = [float(v) if isinstance(v, (int, float)) else None for v in gusts[start:]]
    d_sliced = [
        float(v) if isinstance(v, (int, float)) else None
        for v in dirs[start:start + len(t_sliced)]
    ]
    while len(d_sliced) < len(t_sliced):
        d_sliced.append(None)
    return t_sliced, g_sliced, d_sliced, live


def fetch_forecast_points(cfg: dict, wanted_areas: set[str] | list[str] | None = None) -> list[dict]:
    """Hourly gust + wave for configured sea areas, cached in memory for 15 minutes.

    If wanted_areas is given, only queries and resolves those areas to save bandwidth and latency.
    """
    now = time.time()
    out = []
    points = cfg.get("openmeteo", {}).get("points", [])
    if wanted_areas:
        wanted_set = set(wanted_areas)
        points = [p for p in points if p["name"] in wanted_set]

    for pt in points:
        name = pt["name"]
        cached = _FORECAST_CACHE.get(name)
        if cached:
            ts, item = cached
            if (now - ts) < CACHE_TTL_SEC:
                out.append(item)
                continue

        base = {"latitude": pt["lat"], "longitude": pt["lon"], "forecast_days": 3}
        wt, waves, sea_temp, current_kn, lw = _hourly_marine(
            MARINE,
            {**base, "hourly": "wave_height,sea_surface_temperature,ocean_current_velocity"},
            "openmeteo_marine.json",
        )
        gt, gusts, wind_dirs, lg = _hourly_wind(
            WIND,
            {**base, "hourly": "wind_gusts_10m,wind_direction_10m", "wind_speed_unit": "kn"},
            "openmeteo_wind.json",
        )
        # Wind is required for go/no-go; marine may fail — keep null-aligned waves
        if not lg or not gt or not any(g is not None for g in gusts):
            continue
        if not (lw and wt):
            waves = [None] * len(gt)
        elif len(waves) < len(gt):
            waves = list(waves) + [None] * (len(gt) - len(waves))
        item = {
            "name": pt["name"],
            "lat": pt["lat"],
            "lon": pt["lon"],
            "times": gt,
            "gusts": gusts,
            "waves": waves,
            "wind_dirs": wind_dirs,
            "sea_temp_c": sea_temp if lw else None,
            "current_kn": current_kn if lw else None,
        }
        _FORECAST_CACHE[name] = (now, item)
        out.append(item)

    return out


def fetch_marine_warnings(cfg: dict) -> list[Warning]:
    om = cfg["openmeteo"]
    hours = int(om["hours_ahead"])
    out: list[Warning] = []

    for pt in om["points"]:
        name, lat, lon = pt["name"], pt["lat"], pt["lon"]
        waves, live1 = _series(MARINE, {
            "latitude": lat, "longitude": lon,
            "hourly": "wave_height", "forecast_days": 3,
        }, "openmeteo_marine.json", "wave_height")
        gusts, live2 = _series(WIND, {
            "latitude": lat, "longitude": lon,
            "hourly": "wind_gusts_10m", "wind_speed_unit": "kn", "forecast_days": 3,
        }, "openmeteo_wind.json", "wind_gusts_10m")

        # fixture numbers must never become a published forecast: this exact bug
        # put "dalga 2.7 m, ruzgar 41 kn" (the sample file's values) on the live
        # channel as a real warning for two different sea areas
        if not (live1 and live2):
            continue

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
                id=f"om-{name.lower().replace(' ', '')[:24]}",
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

    return out
