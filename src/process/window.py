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

OK, WATCH, DANGER = "ok", "watch", "danger"
_RANK = {OK: 0, WATCH: 1, DANGER: 2}

# fraction of the limit at which conditions stop being comfortable
WATCH_AT = 0.75


@dataclass
class Window:
    start: str                  # "HH:MM"
    end: str                    # "HH:MM" (exclusive)
    level: str                  # ok | watch | danger
    gust_kn: float = 0.0
    wave_m: float = 0.0

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
    g_lim = float(limits.get("gust_kn", 34))
    w_lim = float(limits.get("wave_m", 2.0))
    g, w = gust or 0.0, wave or 0.0
    if g >= g_lim or w >= w_lim:
        return DANGER
    if g >= g_lim * WATCH_AT or w >= w_lim * WATCH_AT:
        return WATCH
    return OK


def build(name: str, times: list, gusts: list, waves: list, limits: dict,
          hours: int = 18, tz_offset_h: float = 3.0,
          lat: float | None = None, lon: float | None = None) -> AreaOutlook:
    """Collapse consecutive hours that share a level into one window."""
    out = AreaOutlook(name=name, lat=lat, lon=lon)
    n = min(hours, len(times), len(gusts) or hours, len(waves) or hours)
    if n <= 0:
        return out

    cur: Window | None = None
    for i in range(n):
        g = gusts[i] if i < len(gusts) else None
        w = waves[i] if i < len(waves) else None
        lv = level_for(g, w, limits)
        out.max_gust = max(out.max_gust, g or 0.0)
        out.max_wave = max(out.max_wave, w or 0.0)
        start = _local_hhmm(times[i], tz_offset_h)
        end = _local_hhmm(times[i + 1], tz_offset_h) if i + 1 < len(times) else "24:00"
        if cur and cur.level == lv:
            cur.end = end
            cur.gust_kn = max(cur.gust_kn, g or 0.0)
            cur.wave_m = max(cur.wave_m, w or 0.0)
        else:
            cur = Window(start=start, end=end, level=lv, gust_kn=g or 0.0, wave_m=w or 0.0)
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
            prev.gust_kn = max(prev.gust_kn, w.gust_kn)
            prev.wave_m = max(prev.wave_m, w.wave_m)
            continue
        kept.append(w)
    return kept
