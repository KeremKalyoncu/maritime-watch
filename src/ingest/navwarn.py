"""Navigational warnings from the US NGA Maritime Safety Information API.

NAVAREA III covers the Mediterranean and Black Sea. The feed is large, so we keep
only warnings whose text mentions a term from config (Turkey / Marmara / Aegean /
straits / coastal cities).
"""

from __future__ import annotations

from ..model import Warning, now_iso
from ..process.classify import area_centroid
from ._net import get_json

API = ("https://msi.nga.mil/api/publications/navigational-warnings"
       "?status=active&output=json")


def fetch_navwarnings(cfg: dict) -> list[Warning]:
    terms = [t.lower() for t in cfg["navwarn"]["keep_terms"]]
    data, _live = get_json(API, "nga_navwarnings.json")
    rows = []
    if isinstance(data, dict):
        rows = data.get("navigational-warnings") or data.get("warnings") or []
    elif isinstance(data, list):
        rows = data

    out: list[Warning] = []
    for w in rows:
        text = (w.get("text") or w.get("msgText") or "").strip()
        area = (w.get("navArea") or w.get("navarea") or "").strip()
        sub = (w.get("subregion") or "").strip()
        blob = f"{text} {area} {sub}".lower()
        if not text or not any(t in blob for t in terms):
            continue
        num = w.get("msgNumber") or w.get("msgNo") or ""
        year = w.get("msgYear") or w.get("year") or ""
        first = text.split(".")[0][:200] if text else "seyir uyarısı"
        clat, clon = area_centroid(_area_guess(blob))
        out.append(Warning(
            id=f"nw-{year}-{num}" if num else f"nw-{abs(hash(text)) % 100000}",
            headline=f"NAVAREA {area or 'III'} {num}/{year}: {first}",
            area=_area_guess(blob),
            kind="nav-warning",
            severity="minor",
            org="NGA MSI (NAVAREA III)",
            url="https://msi.nga.mil/NavWarnings",
            issued=(w.get("issueDate") or now_iso()),
            raw=text[:800],
            lat=clat, lon=clon,
        ))
    return out[:25]


def _area_guess(blob: str) -> str:
    for key, name in (
        ("marmara", "Marmara Denizi"), ("bosphorus", "İstanbul Boğazı"),
        ("bosporus", "İstanbul Boğazı"), ("dardanelles", "Çanakkale Boğazı"),
        ("aegean", "Ege Denizi"), ("black sea", "Karadeniz"),
        ("iskenderun", "İskenderun Körfezi"), ("mersin", "Mersin Körfezi"),
        ("antalya", "Antalya Körfezi"),
    ):
        if key in blob:
            return name
    return "Türk karasuları civarı"
