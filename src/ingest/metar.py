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
        low_vis = vis * 1609.34 <= m["visibility_m"] if vis < 100 else vis <= m["visibility_m"]
        if gust_kn < m["wind_gust_kn"] and not bad_wx and not low_vis:
            continue

        name = row.get("name") or row.get("icaoId") or "havaalanı"
        bits = []
        if gust_kn >= m["wind_gust_kn"]:
            bits.append(f"rüzgar ~{gust_kn:.0f} kn")
        if bad_wx:
            bits.append(f"hava: {wx}")
        if low_vis:
            bits.append("düşük görüş")
        out.append(Warning(
            id=f"mt-{row.get('icaoId') or name}",
            headline=f"{name}: {', '.join(bits)}",
            area=name,
            kind="metar",
            severity="major" if gust_kn >= m["wind_gust_kn"] + 10 or bad_wx else "minor",
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
