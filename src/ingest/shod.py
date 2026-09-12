"""Parser for SHOD (Seyir, Hidrografi ve Oşinografi Dairesi) NAVTEX navigational warnings.
"""

from __future__ import annotations

import hashlib
import re

from ..model import Warning
from ..process.classify import area_centroid
from ._net import get_text
from .official import _norm

_fetch = get_text

SHOD_DEFAULT_URL = "https://www.shodb.gov.tr/navtex_duyurulari"

# Regex for Turkish / English NAVTEX coordinate pairs:
# e.g. "40 50.20 K - 028 45.10 D" or "40 50.20 N - 028 45.10 E"
_COORD_RE = re.compile(
    r"(\d{2})\s+(\d{1,2}(?:\.\d+)?)\s*([KkGgNnSs])\s*[-–]\s*(\d{2,3})\s+(\d{1,2}(?:\.\d+)?)\s*([DdBbEeWw])"
)


def _parse_coord_pair(match: re.Match) -> tuple[float, float]:
    lat_deg = float(match.group(1))
    lat_min = float(match.group(2))
    lat_dir = match.group(3).upper()
    lat = lat_deg + lat_min / 60.0
    if lat_dir in ("G", "S"):
        lat = -lat

    lon_deg = float(match.group(4))
    lon_min = float(match.group(5))
    lon_dir = match.group(6).upper()
    lon = lon_deg + lon_min / 60.0
    if lon_dir in ("B", "W"):
        lon = -lon

    return round(lat, 4), round(lon, 4)


def scrape_shod(cfg: dict | None = None) -> list[Warning]:
    """Fetch and parse active Turkish NAVTEX messages into Warning models."""
    cfg = cfg or {}
    url = cfg.get("scrape", {}).get("shod_url", SHOD_DEFAULT_URL)
    raw, _live = _fetch(url, "shod_navtex.txt")
    out: list[Warning] = []
    if not raw:
        return out

    # Split by delimiter or blank blocks
    blocks = re.split(r"(?:^|\n)(?:---|\*{3,}|_{3,})(?:\n|$)", raw)
    if len(blocks) <= 1:
        blocks = raw.split("NAVTEX NO:")
        if len(blocks) > 1:
            blocks = ["NAVTEX NO:" + b for b in blocks[1:]]

    for b in blocks:
        text = b.strip()
        if not text or len(text) < 30:
            continue

        no_match = re.search(r"NAVTEX\s+NO:\s*([0-9A-Z/]+)", text, re.IGNORECASE)
        msg_id = no_match.group(1).replace("/", "-") if no_match else None

        # Extract area if explicitly named
        low = _norm(text)
        area = ""
        for sea in ("marmara denizi", "ege denizi", "akdeniz", "karadeniz", "istanbul boğazı", "çanakkale boğazı"):
            if sea in low:
                area = sea.title().replace("Denizi", "Denizi").replace("Boğazı", "Boğazı")
                break

        # Extract coordinates and calculate centroid
        coords: list[tuple[float, float]] = []
        for m in _COORD_RE.finditer(text):
            coords.append(_parse_coord_pair(m))

        if coords:
            clat = round(sum(c[0] for c in coords) / len(coords), 4)
            clon = round(sum(c[1] for c in coords) / len(coords), 4)
        elif area:
            clat, clon = area_centroid(area)
        else:
            clat, clon = None, None

        # Headline generation
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title_line = ""
        for line in lines:
            if "ATIŞ" in line or "EĞİTİM" in line or "ARAŞTIRMA" in line or "KABLO" in line or "SEYİR" in line:
                title_line = line
                break
        if not title_line and lines:
            title_line = lines[0][:100]

        headline = f"NAVTEX {msg_id or ''}: {title_line}".strip(": ")

        warn_id = f"navtex-tr-{msg_id or hashlib.sha1(text.encode()).hexdigest()[:8]}"
        severity = "major" if ("atış" in low or "tehlike" in low) else "minor"

        w = Warning(
            id=warn_id,
            headline=headline,
            area=area,
            severity=severity,
            kind="navtex",
            org="SHOD Seyir Hidrografi",
            url=url,
            raw=text[:600],
            lat=clat,
            lon=clon,
        )
        out.append(w)

    return out[:10]
