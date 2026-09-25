"""Marine + wind forecast from Open-Meteo (free, no API key).

For each configured point we look at the next `hours_ahead` hours and raise a
Warning if the significant wave height or the wind gust crosses the threshold.
This is the reliable replacement for the MGM scrape.

The cycle must pull forecast points **once**: a prior double-pull (warnings then
outlook) rate-limited Open-Meteo and dropped Marmara / Karadeniz from
``outlook.json``.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from ..model import Warning, now_iso
from ._net import get_json

MARINE = "https://marine-api.open-meteo.com/v1/marine"
WIND = "https://api.open-meteo.com/v1/forecast"

_FORECAST_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL_SEC: float = 900.0  # 15 minutes TTL

# Open-Meteo answers in < 1 s when healthy. From GitHub runners a stuck request
# used to sit out the shared 20 s timeout 12 times a cycle (~4 of the 6 minutes);
# fail fast and let the retry pass pick it up instead.
TIMEOUT_SEC = 8
# A few points in flight at once; still far below Open-Meteo's free-tier limit.
MAX_WORKERS = 4


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
    data, live = get_json(f"{url}?{q}", sample, timeout=TIMEOUT_SEC)
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
    data, live = get_json(f"{url}?{q}", sample, timeout=TIMEOUT_SEC)
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
    """Fetch wave height, wave period, sea temp and ocean current in a single combined HTTP request."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    data, live = get_json(f"{url}?{q}", sample, timeout=TIMEOUT_SEC)
    if not data:
        return [], [], [], None, None, live
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    waves = hourly.get("wave_height") or []
    periods = hourly.get("wave_period") or []
    sst = hourly.get("sea_surface_temperature") or []
    cur = hourly.get("ocean_current_velocity") or []
    cutoff = time.strftime("%Y-%m-%dT%H:00", time.gmtime())
    start = next((i for i, t in enumerate(times) if str(t) >= cutoff), 0)
    t_sliced = times[start:]
    # Keep index alignment with times — drop-filter would invent calm hours
    w_sliced = [
        float(v) if isinstance(v, (int, float)) else None for v in waves[start : start + len(t_sliced)]
    ]
    while len(w_sliced) < len(t_sliced):
        w_sliced.append(None)
    p_sliced = [
        float(v) if isinstance(v, (int, float)) else None for v in periods[start : start + len(t_sliced)]
    ]
    while len(p_sliced) < len(t_sliced):
        p_sliced.append(None)
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
    return t_sliced, w_sliced, p_sliced, s_val, c_val, live


def _hourly_wind(url: str, params: dict, sample: str):
    """Gusts, direction and visibility in one request; null cells stay None."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    data, live = get_json(f"{url}?{q}", sample, timeout=TIMEOUT_SEC)
    if not data:
        return [], [], [], [], live
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    gusts = hourly.get("wind_gusts_10m") or []
    dirs = hourly.get("wind_direction_10m") or []
    vis = hourly.get("visibility") or []
    if len(times) != len(gusts):
        return [], [], [], [], live
    cutoff = time.strftime("%Y-%m-%dT%H:00", time.gmtime())
    start = next((i for i, t in enumerate(times) if str(t) >= cutoff), 0)
    t_sliced = times[start:]
    g_sliced = [float(v) if isinstance(v, (int, float)) else None for v in gusts[start:]]
    d_sliced = [
        float(v) if isinstance(v, (int, float)) else None for v in dirs[start : start + len(t_sliced)]
    ]
    while len(d_sliced) < len(t_sliced):
        d_sliced.append(None)
    v_sliced = [float(v) if isinstance(v, (int, float)) else None for v in vis[start : start + len(t_sliced)]]
    while len(v_sliced) < len(t_sliced):
        v_sliced.append(None)
    return t_sliced, g_sliced, d_sliced, v_sliced, live


def _fetch_one_point(pt: dict, *, attempts: int = 3) -> dict | None:
    """One sea area: wind required, marine optional. Retries on transient fail."""
    name = pt["name"]
    base = {"latitude": pt["lat"], "longitude": pt["lon"], "forecast_days": 3}
    wind_key = f"openmeteo_wind:{name}"
    marine_key = f"openmeteo_marine:{name}"

    res_m = res_w = None
    for attempt in range(attempts):
        # Only re-request the leg that failed: re-pulling a good marine answer
        # doubled the timeouts when just the wind endpoint was stuck.
        if res_m is None or not (res_m[-1] and res_m[0]):
            res_m = _hourly_marine(
                MARINE,
                {**base, "hourly": "wave_height,wave_period,sea_surface_temperature,ocean_current_velocity"},
                marine_key,
            )
        if len(res_m) == 6:
            wt, waves, periods, sea_temp, current_kn, lw = res_m
        else:
            wt, waves, sea_temp, current_kn, lw = res_m
            periods = [None] * len(wt)

        if res_w is None or not (res_w[-1] and res_w[0] and any(g is not None for g in res_w[1])):
            res_w = _hourly_wind(
                WIND,
                {**base, "hourly": "wind_gusts_10m,wind_direction_10m,visibility", "wind_speed_unit": "kn"},
                wind_key,
            )
        if len(res_w) == 5:
            gt, gusts, wind_dirs, visibilities, lg = res_w
        else:
            gt, gusts, wind_dirs, lg = res_w
            visibilities = [None] * len(gt)

        if lg and gt and any(g is not None for g in gusts):
            if not (lw and wt):
                waves = [None] * len(gt)
                periods = [None] * len(gt)
            else:
                if len(waves) < len(gt):
                    waves = list(waves) + [None] * (len(gt) - len(waves))
                if len(periods) < len(gt):
                    periods = list(periods) + [None] * (len(gt) - len(periods))
            return {
                "name": name,
                "lat": pt["lat"],
                "lon": pt["lon"],
                "times": gt,
                "gusts": gusts,
                "waves": waves,
                "wave_periods": periods,
                "wind_dirs": wind_dirs,
                "visibilities": visibilities,
                "sea_temp_c": sea_temp if lw else None,
                "current_kn": current_kn if lw else None,
            }
        if attempt + 1 < attempts:
            time.sleep(0.35 * (attempt + 1))
    return None


def fetch_forecast_points(cfg: dict, wanted_areas: set[str] | list[str] | None = None) -> list[dict]:
    """Hourly gust + wave for configured sea areas, cached in memory for 15 minutes.

    If wanted_areas is given, only queries those areas. Retries failed points and
    runs a second pass so Open-Meteo rate-limits do not drop Marmara / Karadeniz.
    """
    now = time.time()
    out: list[dict] = []
    points = list(cfg.get("openmeteo", {}).get("points", []))
    if wanted_areas:
        wanted_set = set(wanted_areas)
        points = [p for p in points if p["name"] in wanted_set]

    def _cached(name: str) -> dict | None:
        cached = _FORECAST_CACHE.get(name)
        if cached:
            ts, item = cached
            if (now - ts) < CACHE_TTL_SEC:
                return item
        return None

    missing: list[dict] = []
    to_fetch: list[dict] = []
    for pt in points:
        hit = _cached(pt["name"])
        if hit:
            out.append(hit)
        else:
            to_fetch.append(pt)

    if to_fetch:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            fetched = list(ex.map(_fetch_one_point, to_fetch))
        for i, pt in enumerate(to_fetch):
            item = fetched[i]
            if item:
                _FORECAST_CACHE[pt["name"]] = (time.time(), item)
                out.append(item)
            else:
                missing.append(pt)

    if missing:
        time.sleep(0.5)
        still: list[str] = []
        for pt in missing:
            name = pt["name"]
            hit = _cached(name)
            if hit:
                out.append(hit)
                continue
            item = _fetch_one_point(pt, attempts=2)
            if item:
                _FORECAST_CACHE[name] = (time.time(), item)
                out.append(item)
            else:
                still.append(name)
        if still:
            print(f"[openmeteo] still missing after retry: {', '.join(still)}")

    by_name = {p["name"]: p for p in out}
    return [by_name[p["name"]] for p in points if p["name"] in by_name]


def warnings_from_forecast(cfg: dict, points: list[dict]) -> list[Warning]:
    """Threshold warnings from an already-fetched forecast (no extra HTTP)."""
    om = cfg["openmeteo"]
    hours = int(om["hours_ahead"])
    out: list[Warning] = []
    for p in points:
        name = p.get("name") or ""
        lat, lon = p.get("lat"), p.get("lon")
        gusts = [g for g in (p.get("gusts") or [])[:hours] if isinstance(g, (int, float))]
        waves = [w for w in (p.get("waves") or [])[:hours] if isinstance(w, (int, float))]
        if not gusts and not waves:
            continue
        max_wave = max(waves) if waves else 0.0
        max_gust = max(gusts) if gusts else 0.0
        if max_wave >= om["wave_m"] or max_gust >= om["wind_gust_kn"]:
            bits = []
            if max_wave:
                bits.append(f"dalga ~{max_wave:.1f} m")
            if max_gust:
                bits.append(f"rüzgar hamlesi ~{max_gust:.0f} kn")
            strong = max_wave >= om["wave_m"] + 1.0 or max_gust >= om["wind_gust_kn"] + 10
            out.append(
                Warning(
                    id=f"om-{name.lower().replace(' ', '')[:24]}",
                    headline=f"{name}: {', '.join(bits)} (önümüzdeki {hours} saat)",
                    area=name,
                    kind="marine-weather",
                    severity="major" if strong else "minor",
                    org="Open-Meteo",
                    url="https://open-meteo.com/en/docs/marine-weather-api",
                    issued=now_iso(),
                    value=round(max_wave, 1) or None,
                    lat=lat,
                    lon=lon,
                )
            )
    return out


def fetch_marine_warnings(cfg: dict) -> list[Warning]:
    """Open-Meteo gale-ish warnings via the shared forecast pull (no second HTTP storm)."""
    return warnings_from_forecast(cfg, fetch_forecast_points(cfg))
