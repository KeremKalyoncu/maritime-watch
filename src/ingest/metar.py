"""Coastal airport weather from aviationweather.gov (free JSON API).

A station raises a Warning when the gust, visibility or present weather looks bad
enough to matter for small craft near that stretch of coast.
"""

from __future__ import annotations

from ..model import Warning, now_iso
from ._net import get_json

API = "https://aviationweather.gov/api/data/metar"

_BAD_WX = ("TS", "SQ", "FC", "GR", "+RA", "+SN", "FG", "BR", "DS", "SS")


def fetch_metar(cfg: dict) -> list[Warning]:
    m = cfg["metar"]
    ids = ",".join(m["stations"])
    data, _live = get_json(f"{API}?ids={ids}&format=json", "metar.json")
    out: list[Warning] = []
    for row in data or []:
        try:
            gust = float(row.get("wgst") or 0)
        except (TypeError, ValueError):
            gust = 0.0
        try:
            wspd = float(row.get("wspd") or 0)
        except (TypeError, ValueError):
            wspd = 0.0
        try:
            vis = float(row.get("visib") or 9999)
        except (TypeError, ValueError):
            vis = 9999.0
        wx = (row.get("wxString") or "").upper()

        gust_kn = max(gust, wspd)
        bad_wx = any(tok in wx for tok in _BAD_WX)
        vis_m = vis * 1609.34 if vis < 100 else vis
        low_vis = vis_m <= m["visibility_m"]
        is_fog = "FG" in wx or (vis_m <= 1000.0)
        if gust_kn < m["wind_gust_kn"] and not bad_wx and not low_vis and not is_fog:
            continue

        name = row.get("name") or row.get("icaoId") or "havaalanı"
        bits = []
        if is_fog:
            bits.append("yoğun sis / düşük görüş (< 1000m)")
        elif low_vis:
            bits.append("düşük görüş")
        if gust_kn >= m["wind_gust_kn"]:
            bits.append(f"rüzgar ~{gust_kn:.0f} kn")
        if bad_wx and not is_fog:
            bits.append(f"hava: {wx}")

        warn_kind = "fog" if is_fog else "metar"
        severity = "major" if (gust_kn >= m["wind_gust_kn"] + 10 or bad_wx or is_fog) else "minor"

        out.append(Warning(
            id=f"mt-{row.get('icaoId') or name}",
            headline=f"{name}: {', '.join(bits)}",
            area=name,
            kind=warn_kind,
            severity=severity,
            org="aviationweather.gov",
            url="https://aviationweather.gov/",
            issued=(row.get("reportTime") or now_iso()),
            lat=_flt(row.get("lat")), lon=_flt(row.get("lon")),
        ))
    return out[:12]


def _flt(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
