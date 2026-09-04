"""Geocoding helpers + status/confidence/severity assignment.

Status ladder:
  signal    - only weak sources (AIS anomaly, SDR keyword)
  probable  - DSC / AIS-SART distress, or an AIS anomaly corroborated by news
  confirmed - an official body (Sahil Güvenlik / AFAD / Valilik) has stated it
"""

from __future__ import annotations

import math

from .. import model
from ..geo import area_centroid, area_of  # noqa: F401  polygon-based, re-exported here

# coastal place -> approx (lat, lon), used to geocode scraped headlines
PLACE_HINTS = {
    # Marmara
    "istanbul": (41.02, 28.97), "silivri": (41.07, 28.25), "büyükçekmece": (41.02, 28.58),
    "şile": (41.18, 29.60), "adalar": (40.86, 29.09), "tuzla": (40.82, 29.30),
    "yalova": (40.66, 29.28), "izmit": (40.76, 29.92), "kocaeli": (40.76, 29.92),
    "gemlik": (40.43, 29.15), "mudanya": (40.37, 28.88), "bursa": (40.37, 28.88),
    "bandırma": (40.35, 27.97), "erdek": (40.40, 27.79), "balıkesir": (40.35, 27.97),
    "marmara adası": (40.59, 27.56), "tekirdağ": (40.98, 27.51), "marmaraereğli": (40.97, 27.95),
    "şarköy": (40.61, 27.11), "gelibolu": (40.41, 26.67),
    # Çanakkale / Kuzey Ege
    "çanakkale": (40.15, 26.41), "gökçeada": (40.19, 25.90), "bozcaada": (39.83, 26.06),
    "ayvacık": (39.60, 26.40), "edremit": (39.59, 26.94), "ayvalık": (39.31, 26.69),
    "dikili": (39.07, 26.89), "foça": (38.67, 26.75),
    # İzmir / Orta-Güney Ege
    "izmir": (38.43, 27.14), "çeşme": (38.32, 26.30), "urla": (38.32, 26.76),
    "seferihisar": (38.20, 26.84), "kuşadası": (37.86, 27.26), "aydın": (37.86, 27.26),
    "didim": (37.38, 27.26), "bodrum": (37.03, 27.43), "muğla": (36.75, 27.90),
    "datça": (36.73, 27.68), "marmaris": (36.85, 28.27), "göcek": (36.75, 28.94),
    "fethiye": (36.62, 29.11), "kaş": (36.20, 29.64), "kalkan": (36.26, 29.41),
    "gökova": (36.98, 28.00),
    # Akdeniz
    "antalya": (36.88, 30.70), "kemer": (36.60, 30.56), "finike": (36.30, 30.15),
    "alanya": (36.54, 32.00), "anamur": (36.07, 32.84), "silifke": (36.38, 33.93),
    "mersin": (36.80, 34.63), "adana": (36.78, 35.30), "karataş": (36.57, 35.38),
    "iskenderun": (36.58, 36.17), "hatay": (36.20, 35.95), "samandağ": (36.08, 35.95),
    # Karadeniz
    "kıyıköy": (41.64, 28.10), "kırklareli": (41.64, 28.10), "karasu": (41.11, 30.68),
    "kdz ereğli": (41.28, 31.42), "ereğli": (41.28, 31.42), "zonguldak": (41.45, 31.79),
    "bartın": (41.63, 32.34), "amasra": (41.75, 32.39), "kastamonu": (41.92, 33.77),
    "inebolu": (41.98, 33.76), "sinop": (42.03, 35.15), "samsun": (41.29, 36.33),
    "ordu": (41.00, 37.87), "giresun": (40.92, 38.39), "trabzon": (41.00, 39.72),
    "rize": (41.02, 40.52), "artvin": (41.42, 41.42), "hopa": (41.42, 41.42),
    # yakın sular (haber metinlerinde sık geçer)
    "girne": (35.34, 33.32), "gazimağusa": (35.12, 33.94), "lefkoşa": (35.19, 33.36),
}

SOURCE_WEIGHT = {
    "official": 0.60, "navtex": 0.45, "nav-warning": 0.40, "dsc": 0.55,
    "ais-sart": 0.55, "ais-safety": 0.35, "news": 0.30,
    "ais-anomaly": 0.25, "sdr": 0.15,
}

# major ports / harbours, used for the "nearest port" line in alerts
PORTS = {
    "İstanbul": (41.02, 28.97), "Kadıköy": (40.99, 29.02), "Tuzla": (40.82, 29.30),
    "Gebze": (40.79, 29.43), "İzmit": (40.76, 29.92), "Yalova": (40.66, 29.28),
    "Mudanya": (40.38, 28.88), "Gemlik": (40.43, 29.15), "Bandırma": (40.35, 27.97),
    "Erdek": (40.40, 27.79), "Marmara Adası": (40.59, 27.56), "Tekirdağ": (40.98, 27.51),
    "Silivri": (41.07, 28.25), "Şile": (41.18, 29.60), "Çanakkale": (40.15, 26.41),
    "Gelibolu": (40.41, 26.67), "Bozcaada": (39.83, 26.06), "Ayvalık": (39.31, 26.69),
    "İzmir": (38.43, 27.14), "Çeşme": (38.32, 26.30), "Kuşadası": (37.86, 27.26),
    "Bodrum": (37.03, 27.43), "Marmaris": (36.85, 28.27), "Fethiye": (36.62, 29.11),
    "Antalya": (36.83, 30.60), "Alanya": (36.54, 32.00), "Mersin": (36.80, 34.63),
    "İskenderun": (36.58, 36.17), "Zonguldak": (41.45, 31.79), "Ereğli": (41.28, 31.42),
    "Bartın": (41.63, 32.34), "Sinop": (42.03, 35.15), "Samsun": (41.29, 36.33),
    "Ordu": (41.00, 37.87), "Giresun": (40.92, 38.39), "Trabzon": (41.00, 39.72),
    "Rize": (41.02, 40.52), "Hopa": (41.42, 41.42),
}

_COMPASS = ["K", "KKD", "KD", "DKD", "D", "DGD", "GD", "GGD",
            "G", "GGB", "GB", "BGB", "B", "BKB", "KB", "KKB"]


def _haversine_nm(lat1, lon1, lat2, lon2) -> float:
    r = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _bearing(lat1, lon1, lat2, lon2) -> str:
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.cos(math.radians(lon2 - lon1)))
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return _COMPASS[round(deg / 22.5) % 16]


def nearest_port(lat, lon):
    """(name, distance_nm, compass_dir_from_port) of the closest listed port."""
    if lat is None or lon is None:
        return None
    best = None
    for name, (pla, plo) in PORTS.items():
        d = _haversine_nm(lat, lon, pla, plo)
        if best is None or d < best[1]:
            best = (name, d, _bearing(pla, plo, lat, lon))
    return best


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


def classify(inc) -> model.Incident:
    kinds = {s.kind for s in inc.sources}

    conf = min(sum(SOURCE_WEIGHT.get(k, 0.1) for k in kinds), 0.98)

    if inc.status in ("resolved", "false-positive"):
        status = inc.status
    elif "official" in kinds:
        status = "confirmed"
    elif kinds & {"dsc", "ais-sart"} or ("ais-anomaly" in kinds and "news" in kinds):
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
