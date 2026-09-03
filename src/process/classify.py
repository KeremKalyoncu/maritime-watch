"""Geocoding helpers + status/confidence/severity assignment.

Status ladder:
  signal    - only weak sources (AIS anomaly, SDR keyword)
  probable  - DSC distress, or an AIS anomaly corroborated by news
  confirmed - an official body (Sahil Güvenlik / AFAD / Valilik) has stated it
"""

from __future__ import annotations

from .. import model

# name, lat_min, lat_max, lon_min, lon_max  (most specific first)
SEA_AREAS = [
    ("İstanbul Boğazı", 41.00, 41.28, 28.90, 29.20),
    ("Çanakkale Boğazı", 39.95, 40.55, 26.10, 26.75),
    ("Marmara Denizi", 40.30, 41.05, 26.70, 29.95),
    ("Kuzey Ege", 38.50, 40.60, 24.50, 27.20),
    ("Güney Ege", 36.00, 38.50, 24.50, 28.60),
    ("Antalya Körfezi / Batı Akdeniz", 35.80, 37.00, 29.00, 32.20),
    ("Mersin–İskenderun / Doğu Akdeniz", 35.80, 37.10, 32.20, 36.60),
    ("Batı Karadeniz", 41.10, 43.60, 27.30, 35.10),
    ("Doğu Karadeniz", 40.90, 42.60, 35.10, 42.20),
]

# coastal place -> approx (lat, lon), used to geocode scraped headlines
PLACE_HINTS = {
    "istanbul": (41.02, 28.97), "İstanbul": (41.02, 28.97),
    "çanakkale": (40.15, 26.41), "gelibolu": (40.41, 26.67),
    "izmir": (38.43, 27.14), "çeşme": (38.32, 26.30), "foça": (38.67, 26.75),
    "ayvalık": (39.31, 26.69), "dikili": (39.07, 26.89), "kuşadası": (37.86, 27.26),
    "didim": (37.38, 27.26), "bodrum": (37.03, 27.43), "datça": (36.73, 27.68),
    "marmaris": (36.85, 28.27), "fethiye": (36.62, 29.11), "kaş": (36.20, 29.64),
    "kalkan": (36.26, 29.41), "antalya": (36.88, 30.70), "alanya": (36.54, 32.00),
    "mersin": (36.80, 34.63), "iskenderun": (36.58, 36.17), "hatay": (36.20, 35.95),
    "samsun": (41.29, 36.33), "sinop": (42.03, 35.15), "zonguldak": (41.45, 31.79),
    "trabzon": (41.00, 39.72), "rize": (41.02, 40.52), "ordu": (41.00, 37.87),
    "giresun": (40.92, 38.39), "bartın": (41.63, 32.34), "kdz ereğli": (41.28, 31.42),
    "şile": (41.18, 29.60), "mudanya": (40.37, 28.88), "bandırma": (40.35, 27.97),
    "tekirdağ": (40.98, 27.51), "silivri": (41.07, 28.25), "yalova": (40.66, 29.28),
    "gökçeada": (40.19, 25.90), "bozcaada": (39.83, 26.06),
}

SOURCE_WEIGHT = {
    "official": 0.60, "navtex": 0.45, "dsc": 0.50,
    "news": 0.30, "ais-anomaly": 0.25, "sdr": 0.15,
}


def area_of(lat, lon) -> str:
    if lat is None or lon is None:
        return ""
    for name, la0, la1, lo0, lo1 in SEA_AREAS:
        if la0 <= lat <= la1 and lo0 <= lon <= lo1:
            return name
    return "Türk karasuları civarı"


def area_centroid(name: str):
    """(lat, lon) centre of a named sea area, for placing a warning on the map."""
    if not name:
        return None, None
    low = name.lower()
    for aname, la0, la1, lo0, lo1 in SEA_AREAS:
        if aname.lower() in low or low in aname.lower():
            return round((la0 + la1) / 2, 3), round((lo0 + lo1) / 2, 3)
    return None, None


_TR_LOWER = str.maketrans("İIŞĞÜÖÇ", "iışğüöç")


def _norm(s: str) -> str:
    return s.translate(_TR_LOWER).lower()


def place_hint(text: str):
    """Return (lat, lon, area) for the first known coastal place named in text."""
    low = _norm(text)
    for name, (lat, lon) in PLACE_HINTS.items():
        if _norm(name) in low:
            return lat, lon, area_of(lat, lon) or name.title()
    return None, None, ""


def classify(inc) -> "model.Incident":
    kinds = {s.kind for s in inc.sources}

    conf = min(sum(SOURCE_WEIGHT.get(k, 0.1) for k in kinds), 0.98)

    if inc.status in ("resolved", "false-positive"):
        status = inc.status
    elif "official" in kinds:
        status = "confirmed"
    elif "dsc" in kinds or ("ais-anomaly" in kinds and "news" in kinds):
        status = "probable"
    else:
        status = "signal"

    inc.status = status
    inc.confidence = round(conf, 2)
    if not inc.area:
        inc.area = area_of(inc.lat, inc.lon)

    if inc.casualties and inc.casualties > 0:
        inc.severity = "critical"
    elif status in ("confirmed", "probable"):
        inc.severity = "major"
    elif status == "resolved":
        inc.severity = "info"
    else:
        inc.severity = "minor"
    return inc
