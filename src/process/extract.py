"""Pull structured facts out of Turkish incident text (news headlines, official
statements): vessel name, coordinates, casualty counts, place names.

Rules + a gazetteer, no ML dependency. Conservative: it would rather return
nothing than a wrong guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..geo import area_of
from .classify import PLACE_HINTS, _norm

# vessel-type word + any Turkish case suffix (gemisi, gemisinin, teknesiyle, ...)
_VW = r"(?:gemi|tekne|şile[pb]|yat|kotra|feribot|römorkör|tanker|balıkçı\s+teknesi|sürat\s+teknesi)\w*"

# "ALSU gemisi" / "Alsu isimli tekne" / 'Alsu' gemisi / “Alsu” gemi
_VESSEL_RE = [
    re.compile(r"[«\"'“]([A-Za-zÇĞİÖŞÜçğıöşü][\wÇĞİÖŞÜçğıöşü .-]{1,28}?)[»\"'”]\s*(?:isimli\s+|adlı\s+)?" + _VW,
               re.IGNORECASE),
    re.compile(r"\b([A-ZÇĞİÖŞÜ][A-Za-z0-9ÇĞİÖŞÜçğıöşü .-]{2,26}?)\s+(?:isimli|adlı)\s+" + _VW),
    re.compile(r"\b([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9]{1,}(?:[ .-][A-ZÇĞİÖŞÜ0-9]{1,}){0,3})\s+" + _VW),
]

_CAS_RE = re.compile(
    r"(\d{1,3})\s*(?:[a-zçğıöşü]+\s+){0,2}?"          # optional adjectives ("20 düzensiz göçmen")
    r"(?:kişi|can|mürettebat|göçmen|çocuk|yolcu|denizci|balıkçı|tayfa|personel)"
    r"(?:[^.]{0,40}?(kayıp|yaralı|öl|hayat|mahsur|kurtar|aran|tahliye))?",
    re.IGNORECASE,
)
_CAS_KEEP = ("kayıp", "yaralı", "öl", "hayat", "mahsur", "aran")

# 40°55'K 28°10'D   |   40 55 12 N 28 10 30 E   |   40.912 N, 28.241 E   |   40.91, 28.24
_DMS_RE = re.compile(
    r"(\d{1,2})[°º:\s]\s*(\d{1,2})(?:['′\s]\s*(\d{1,2}(?:\.\d+)?)?[\"″]?)?\s*([KNGSkngs])"
    r"[,;\s/]+(\d{1,3})[°º:\s]\s*(\d{1,2})(?:['′\s]\s*(\d{1,2}(?:\.\d+)?)?[\"″]?)?\s*([DEBWdebw])"
)
_DEC_RE = re.compile(r"(-?\d{1,2}\.\d{2,6})\s*([KNkn])?\s*[,;\s]+\s*(-?\d{1,3}\.\d{2,6})\s*([DEde])?")

_TR_BBOX = (34.0, 44.0, 24.0, 43.0)  # lat_min, lat_max, lon_min, lon_max


@dataclass
class Extracted:
    vessel: str | None = None
    lat: float | None = None
    lon: float | None = None
    area: str = ""
    casualties: int | None = None
    places: list[str] = field(default_factory=list)


def _in_tr(lat, lon) -> bool:
    a, b, c, d = _TR_BBOX
    return a <= lat <= b and c <= lon <= d


def _dms(d, m, s, hemi) -> float:
    val = float(d) + float(m) / 60 + (float(s) if s else 0) / 3600
    return -val if hemi.upper() in ("G", "S", "B", "W") else val


def coordinates(text: str):
    m = _DMS_RE.search(text)
    if m:
        lat = _dms(m.group(1), m.group(2), m.group(3), m.group(4))
        lon = _dms(m.group(5), m.group(6), m.group(7), m.group(8))
        if _in_tr(lat, lon):
            return round(lat, 4), round(lon, 4)
    m = _DEC_RE.search(text)
    if m:
        lat = float(m.group(1))
        lon = float(m.group(3))
        if (m.group(2) or "").upper() in ("", "K", "N") and _in_tr(lat, lon):
            return round(lat, 4), round(lon, 4)
    return None, None


def vessel_name(text: str):
    stop = {"SAHİL", "SAHIL", "GÜVENLİK", "GUVENLIK", "KURTARMA", "ARAMA", "DENİZ",
            "DENIZ", "SON", "DAKİKA", "DAKIKA", "HABERİ", "HABERI", "TÜRK", "TURK"}
    for rx in _VESSEL_RE:
        for m in rx.finditer(text):
            name = " ".join(m.group(1).split()).strip(" .,-")
            words = name.upper().split()
            if 1 <= len(words) <= 4 and not any(w in stop for w in words) and len(name) >= 3:
                return name
    return None


def casualties(text: str):
    best = None
    for m in _CAS_RE.finditer(text):
        n = int(m.group(1))
        if n > 500:
            continue
        ctx = (m.group(2) or "")
        if best is None or (any(k in ctx.lower() for k in _CAS_KEEP) and n <= (best or n)):
            best = n
    return best


def places(text: str):
    low = _norm(text)
    hits = []
    for name, (lat, lon) in PLACE_HINTS.items():
        if _norm(name) in low and name.title() not in hits:
            hits.append((name.title(), lat, lon))
    return hits


def extract(text: str) -> Extracted:
    e = Extracted()
    e.vessel = vessel_name(text)
    e.casualties = casualties(text)
    lat, lon = coordinates(text)
    pl = places(text)
    e.places = [p[0] for p in pl]
    if lat is not None:
        e.lat, e.lon = lat, lon
    elif pl:
        e.lat, e.lon = pl[0][1], pl[0][2]
    e.area = area_of(e.lat, e.lon)
    return e
