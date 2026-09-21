"""Turn an hourly forecast into the answer a fisherman actually needs.

A maximum ("bugün en fazla 25 kn") does not help anyone decide anything. The
question at 04:00 is "can I go out, and until when", so the forecast has to come
back as time windows: calm until one o'clock, then six Beaufort until dark.

Thresholds are per boat class. Multi-hazard decision engine integrates:
- Wind gusts & 16-point nautical compass direction
- Wave height & period (steep breaking wave detection)
- Coastal visibility / fog gate (<300m danger, <1000m watch)
- Solar sunset ceiling (safe return before dark)
"""

from __future__ import annotations

import calendar
import time
from dataclasses import dataclass, field

from .astronomy import calculate_sun_times
from .marine_physics import analyze_wave_steepness, degree_to_compass_tr

OK, WATCH, DANGER, UNKNOWN = "ok", "watch", "danger", "unknown"
# unknown ranks with watch: never report a day as "all clear" if hours lack data
_RANK = {OK: 0, UNKNOWN: 1, WATCH: 1, DANGER: 2}

# fraction of the limit at which conditions stop being comfortable
WATCH_AT = 0.75


def _max_opt(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


@dataclass
class Window:
    start: str  # "HH:MM"
    end: str  # "HH:MM" (exclusive)
    level: str  # ok | watch | danger | unknown
    gust_kn: float | None = None
    wave_m: float | None = None
    dominant_wind: str = ""
    hazard_reason: str | None = None

    @property
    def hours(self) -> int:
        return (_mins(self.end) - _mins(self.start)) // 60


@dataclass
class AreaOutlook:
    name: str
    lat: float | None = None
    lon: float | None = None
    windows: list[Window] = field(default_factory=list)
    max_gust: float = 0.0
    max_wave: float = 0.0
    sunset_time: str = ""
    safe_cutoff: str = ""
    cur_wind_name: str = ""
    cur_wind_dir: float | None = None
    cur_wave_period: float | None = None
    cur_visibility_km: float | None = None
    steepness_hazard: bool = False
    fog_hazard: bool = False
    orkoz_hazard: bool = False
    data_quality: str = "ok"

    @property
    def worst(self) -> str:
        return max((w.level for w in self.windows), key=lambda x: _RANK[x], default=OK)

    @property
    def first_danger(self) -> Window | None:
        return next((w for w in self.windows if w.level == DANGER), None)

    @property
    def first_watch(self) -> Window | None:
        return next((w for w in self.windows if w.level == WATCH), None)


def return_by(area: AreaOutlook) -> str | None:
    """Earliest hour the skipper should plan to be back in harbour.

    Prefer the first danger window; otherwise the first watch window.
    If conditions stop being safe, clamps against safe sunset cutoff if present.
    Calm days return None (no fabricated deadline).
    """
    cand: str | None = None
    if area.first_danger:
        cand = area.first_danger.start
    elif area.first_watch:
        cand = area.first_watch.start

    if cand and area.safe_cutoff:
        if _mins(area.safe_cutoff) < _mins(cand):
            return area.safe_cutoff
        return cand
    return cand


def window_to_dict(w: Window) -> dict:
    return {
        "start": w.start,
        "end": w.end,
        "level": w.level,
        "gust_kn": None if w.gust_kn is None else round(float(w.gust_kn), 1),
        "wave_m": None if w.wave_m is None else round(float(w.wave_m), 2),
        "dominant_wind": w.dominant_wind,
        "hazard_reason": w.hazard_reason,
    }


def area_to_public_dict(area: AreaOutlook) -> dict:
    """Serialize AreaOutlook for outlook.json / bot cache consumers."""
    fd = area.first_danger
    return {
        "name": area.name,
        "lat": area.lat,
        "lon": area.lon,
        "windows": [window_to_dict(w) for w in area.windows],
        "max_gust": round(float(area.max_gust), 1),
        "max_wave": round(float(area.max_wave), 2),
        "first_danger_start": fd.start if fd else None,
        "return_by": return_by(area),
        "worst": area.worst,
        "sunset_time": area.sunset_time,
        "safe_cutoff": area.safe_cutoff,
        "cur_wind_name": area.cur_wind_name,
        "cur_wind_dir": area.cur_wind_dir,
        "cur_wave_period": area.cur_wave_period,
        "cur_visibility_km": area.cur_visibility_km,
        "steepness_hazard": area.steepness_hazard,
        "fog_hazard": area.fog_hazard,
        "orkoz_hazard": area.orkoz_hazard,
        "data_quality": area.data_quality,
    }


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _local_hhmm(iso: str, tz_offset_h: float) -> str:
    """Open-Meteo answers in UTC; a fisherman reads local time."""
    try:
        t = time.strptime(str(iso)[:16], "%Y-%m-%dT%H:%M")
    except ValueError:
        return "??:??"
    e = calendar.timegm(t) + int(tz_offset_h * 3600)
    return time.strftime("%H:%M", time.gmtime(e))


def level_for(
    gust: float | None,
    wave: float | None,
    limits: dict,
    period: float | None = None,
    visibility: float | None = None,
    wind_dir: float | None = None,
) -> str:
    """Classify one hour with multi-hazard physical gates.
    Missing measurements are never treated as calm (0).
    """
    # KAPI 1: Sis Kapısı (Hard Fog Gate)
    # Visibility in meters: <300m is dense fog (danger)
    if visibility is not None and visibility < 300:
        return DANGER

    g_lim = float(limits.get("gust_kn", 34))
    w_lim = float(limits.get("wave_m", 2.0))

    # KAPI 2: Dik Dalga Çarpanı (Wave Steepness Penalty)
    if wave is not None and period is not None:
        steep = analyze_wave_steepness(wave, period)
        if steep.is_steep:
            w_lim = w_lim * 0.7  # %30 daha sıkı eşik

    if gust is None and wave is None and visibility is None:
        return UNKNOWN

    danger = False
    watch = False

    # KAPI 1 (Ek): Kıyı sisi / pus uyarısı
    if visibility is not None and visibility < 1000:
        watch = True

    if gust is not None:
        if gust >= g_lim:
            danger = True
        elif gust >= g_lim * WATCH_AT:
            watch = True

    if wave is not None:
        if wave >= w_lim:
            danger = True
        elif wave >= w_lim * WATCH_AT:
            watch = True

    if danger:
        return DANGER
    if watch:
        return WATCH
    return OK


def build(
    name: str,
    times: list,
    gusts: list,
    waves: list,
    limits: dict,
    hours: int = 18,
    tz_offset_h: float = 3.0,
    lat: float | None = None,
    lon: float | None = None,
    wave_periods: list | None = None,
    wind_dirs: list | None = None,
    visibilities: list | None = None,
    date: str | None = None,
) -> AreaOutlook:
    """Collapse consecutive hours that share a level into one window."""
    out = AreaOutlook(name=name, lat=lat, lon=lon)
    if not times:
        return out
    usable = max(len(gusts), len(waves))
    if usable <= 0:
        return out
    n = min(hours, len(times), usable)

    # Calculate astronomical sun cycle if coordinates available
    if lat is not None and lon is not None:
        ref_date = date or (times[0].split("T")[0] if times and "T" in str(times[0]) else None)
        sun = calculate_sun_times(lat, lon, date=ref_date, tz_offset_hours=tz_offset_h)
        out.sunset_time = sun.sunset_time
        out.safe_cutoff = sun.safe_return_cutoff

    # Check current physical conditions for metadata
    if wind_dirs and wind_dirs[0] is not None:
        out.cur_wind_dir = float(wind_dirs[0])
        out.cur_wind_name = degree_to_compass_tr(out.cur_wind_dir)

    if wave_periods and wave_periods[0] is not None:
        out.cur_wave_period = float(wave_periods[0])

    if visibilities and visibilities[0] is not None:
        out.cur_visibility_km = round(float(visibilities[0]) / 1000.0, 1)
        if float(visibilities[0]) < 1000:
            out.fog_hazard = True

    # Check if waves are missing
    if not any(w is not None for w in waves[:n]):
        out.data_quality = "partial" if any(g is not None for g in gusts[:n]) else "unknown"

    cur: Window | None = None
    for i in range(n):
        g = gusts[i] if i < len(gusts) else None
        w = waves[i] if i < len(waves) else None
        p = wave_periods[i] if wave_periods and i < len(wave_periods) else None
        d = wind_dirs[i] if wind_dirs and i < len(wind_dirs) else None
        v = visibilities[i] if visibilities and i < len(visibilities) else None

        lv = level_for(g, w, limits, period=p, visibility=v, wind_dir=d)
        w_name = degree_to_compass_tr(d) if d is not None else ""

        # Hazard description
        reason = None
        if v is not None and v < 300:
            reason = "Yoğun Sis (Görüş < 300m)"
        elif v is not None and v < 1000:
            reason = "Kıyı Sisi / Pus"
        elif w is not None and p is not None:
            steep = analyze_wave_steepness(w, p)
            if steep.is_steep:
                out.steepness_hazard = True
                reason = steep.reason

        if g is not None:
            out.max_gust = max(out.max_gust, float(g))
        if w is not None:
            out.max_wave = max(out.max_wave, float(w))

        start = _local_hhmm(times[i], tz_offset_h)
        end = _local_hhmm(times[i + 1], tz_offset_h) if i + 1 < len(times) else "24:00"

        if cur and cur.level == lv:
            cur.end = end
            cur.gust_kn = _max_opt(cur.gust_kn, g)
            cur.wave_m = _max_opt(cur.wave_m, w)
            if not cur.hazard_reason and reason:
                cur.hazard_reason = reason
        else:
            cur = Window(
                start=start,
                end=end,
                level=lv,
                gust_kn=g,
                wave_m=w,
                dominant_wind=w_name,
                hazard_reason=reason,
            )
            out.windows.append(cur)

    # an hour of calm between two blows is noise, not a window anyone can use
    out.windows = _merge_slivers(out.windows)
    return out


def _merge_slivers(ws: list[Window], min_hours: int = 2) -> list[Window]:
    if len(ws) < 3:
        return ws
    kept: list[Window] = [ws[0]]
    for w in ws[1:]:
        prev = kept[-1]
        if w.hours < min_hours and _RANK[w.level] < _RANK[prev.level]:
            prev.end = w.end  # swallow the short lull into the rougher block
            continue
        if w.level == prev.level:
            prev.end = w.end
            prev.gust_kn = _max_opt(prev.gust_kn, w.gust_kn)
            prev.wave_m = _max_opt(prev.wave_m, w.wave_m)
            continue
        kept.append(w)
    return kept
