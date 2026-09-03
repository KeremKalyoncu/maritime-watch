"""Global Disaster Alert and Coordination System (GDACS) events, via the RSS feed.

Kept only when the epicentre falls inside the region bbox (or the country is
Turkey) and the alert level / event type is one we care about.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from ..model import Warning, now_iso
from ._net import get_text

RSS = "https://www.gdacs.org/xml/rss.xml"

_TYPE_TR = {"TC": "tropik fırtına", "FL": "sel", "EQ": "deprem",
            "WF": "orman yangını", "DR": "kuraklık", "VO": "volkan"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _bbox(lat, lon, b) -> bool:
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]


def fetch_gdacs(cfg: dict) -> list[Warning]:
    g = cfg["gdacs"]
    bbox = cfg["region"]["bbox"]
    raw, _live = get_text(RSS, "gdacs_rss.xml")
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    out: list[Warning] = []
    for item in root.iter("item"):
        f = {_local(c.tag): (c.text or "").strip() for c in item}
        etype = f.get("eventtype")
        level = f.get("alertlevel")
        if etype not in g["event_types"] or level not in g["alert_levels"]:
            continue
        try:
            lat = float(f.get("lat"))
            lon = float(f.get("long") or f.get("lon"))
        except (TypeError, ValueError):
            lat = lon = None
        country = (f.get("country") or "").lower()
        if not ((lat is not None and _bbox(lat, lon, bbox)) or "turk" in country):
            continue

        title = f.get("title") or _TYPE_TR.get(etype, etype)
        out.append(Warning(
            id=f"gd-{f.get('guid') or abs(hash(title)) % 100000}",
            headline=f"GDACS {level}: {_TYPE_TR.get(etype, etype)} - {title[:200]}",
            area=f.get("country") or cfg["region"]["name"],
            kind="gdacs",
            severity="major" if level == "Red" else "minor",
            org="GDACS",
            url=f.get("link") or "https://www.gdacs.org/",
            issued=f.get("pubDate") or now_iso(),
            lat=lat, lon=lon,
        ))
    return out[:15]
