"""Turn an hourly forecast into the answer a fisherman actually needs.

A maximum ("bugün en fazla 25 kn") does not help anyone decide anything. The
question at 04:00 is "can I go out, and until when", so the forecast has to come
back as time windows: calm until one o'clock, then six Beaufort until dark.

Thresholds are per boat class. The old single threshold was 34 kn / 2.0 m, which
in nine days of real Turkish coastal data was crossed 4 times and 0 times - it
was set for a cargo ship, while the channel claims to serve small craft. At the
small-craft limit the same nine days had 371 point-hours of unsafe wind.
"""

from __future__ import annotations

import calendar
import time
from dataclasses import dataclass, field

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
    start: str                  # "HH:MM"
    end: str                    # "HH:MM" (exclusive)
    level: str                  # ok | watch | danger | unknown
    gust_kn: float | None = None
    wave_m: float | None = None

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
    Calm days return None (no fabricated deadline).
    """
    if area.first_danger:
        return area.first_danger.start
    if area.first_watch:
        return area.first_watch.start
    return None


def window_to_dict(w: Window) -> dict:
    return {
        "start": w.start,
        "end": w.end,
        "level": w.level,
        "gust_kn": None if w.gust_kn is None else round(float(w.gust_kn), 1),
        "wave_m": None if w.wave_m is None else round(float(w.wave_m), 2),
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


def level_for(gust: float | None, wave: float | None, limits: dict) -> str:
    """Classify one hour. Missing measurements are never treated as calm (0)."""
    g_lim = float(limits.get("gust_kn", 34))
    w_lim = float(limits.get("wave_m", 2.0))
    if gust is None and wave is None:
        return UNKNOWN

    danger = False
    watch = False
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


def build(name: str, times: list, gusts: list, waves: list, limits: dict,
          hours: int = 18, tz_offset_h: float = 3.0,
          lat: float | None = None, lon: float | None = None) -> AreaOutlook:
    """Collapse consecutive hours that share a level into one window."""
    out = AreaOutlook(name=name, lat=lat, lon=lon)
    if not times:
        return out
    usable = max(len(gusts), len(waves))
    if usable <= 0:
        return out
    n = min(hours, len(times), usable)

    cur: Window | None = None
    for i in range(n):
        g = gusts[i] if i < len(gusts) else None
        w = waves[i] if i < len(waves) else None
        lv = level_for(g, w, limits)
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
        else:
            cur = Window(start=start, end=end, level=lv, gust_kn=g, wave_m=w)
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
            prev.end = w.end          # swallow the short lull into the rougher block
            continue
        if w.level == prev.level:
            prev.end = w.end
            prev.gust_kn = _max_opt(prev.gust_kn, w.gust_kn)
            prev.wave_m = _max_opt(prev.wave_m, w.wave_m)
            continue
        kept.append(w)
    return kept
