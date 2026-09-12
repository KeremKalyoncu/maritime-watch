"""Kandilli Rasathanesi (KOERI) coastal earthquakes parser.

Boğaziçi Üniversitesi Kandilli Rasathanesi ve Deprem Araştırma Enstitüsü (BDTİM).
Fetches recent Turkish earthquakes, filters for coastal proximity (<= 40 NM)
and magnitude >= min_mag.
"""

from __future__ import annotations

import re
import time

from ..model import Warning, now_iso
from ..process.classify import nearest_port
from ._net import get_text

KOERI_URL = "http://www.koeri.boun.edu.tr/scripts/lst9.asp"
COASTAL_NM = 40
_SEA_WORDS = ("deniz", "körfez", "açık", "boğaz", "ada", "sea", "gulf", "aegean", "marmara")


def _coastal(lat: float, lon: float, place: str) -> bool:
    if any(w in place.lower() for w in _SEA_WORDS):
        return True
    np = nearest_port(lat, lon)
    return np is not None and np[1] <= COASTAL_NM


def _bbox(lat: float, lon: float, b: dict) -> bool:
    return b["lat_min"] <= lat <= b["lat_max"] and b["lon_min"] <= lon <= b["lon_max"]


def _mk(lat: float, lon: float, mag: float, place: str, ts: str) -> Warning:
    # Match quakes.py place naming logic and ID convention
    from .quakes import place_tr
    area_name = place_tr(place)
    return Warning(
        id=f"eq-kandilli-{round(lat, 2)}-{round(lon, 2)}-{str(ts)[:16]}",
        headline=f"Deprem M{mag:.1f} - {area_name}",
        area=area_name,
        kind="earthquake",
        severity="major" if mag >= 4.5 else "minor",
        org="Kandilli Rasathanesi",
        url="http://www.koeri.boun.edu.tr/",
        issued=str(ts),
        value=round(mag, 1),
        lat=lat,
        lon=lon,
    )


def fetch_kandilli(cfg: dict) -> list[Warning]:
    q = cfg.get("quakes", {})
    bbox = cfg.get("region", {}).get("bbox", {"lat_min": 35.0, "lat_max": 43.5, "lon_min": 25.0, "lon_max": 42.5})
    min_mag = float(q.get("min_mag", 3.8))
    hours_back = float(q.get("hours_back", 24))
    cutoff_ts = time.time() - hours_back * 3600

    raw, _live = get_text(KOERI_URL, "kandilli_quakes.html", timeout=15)
    if not raw:
        return []

    # Extract <pre> block
    pre_match = re.search(r"<pre>(.*?)</pre>", raw, re.DOTALL | re.IGNORECASE)
    content = pre_match.group(1) if pre_match else raw

    out: list[Warning] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(("-", "Tarih", ".")):
            continue
        toks = line.split()
        if len(toks) < 9:
            continue

        # Check date & time format
        if not re.match(r"^\d{4}\.\d{2}\.\d{2}$", toks[0]) or not re.match(r"^\d{2}:\d{2}:\d{2}$", toks[1]):
            continue

        try:
            lat = float(toks[2])
            lon = float(toks[3])
        except ValueError:
            continue

        # Magnitude: take max of available non-empty magnitudes (MD, ML, Mw)
        mags = []
        for m_str in (toks[5], toks[6], toks[7]):
            try:
                mags.append(float(m_str))
            except ValueError:
                pass

        if not mags:
            continue
        mag = max(mags)

        # Place text
        solution_qualities = {"İlksel", "Ýlksel", "Otomatik", "Revize", "ilksel", "revize"}
        place_tokens = toks[8:-1] if toks[-1] in solution_qualities else toks[8:]
        place = " ".join(place_tokens).strip()

        # Parse event time
        try:
            struct_t = time.strptime(f"{toks[0]} {toks[1]}", "%Y.%m.%d %H:%M:%S")
            ev_epoch = time.mktime(struct_t)
            if _live and ev_epoch < cutoff_ts:
                continue
            iso_ts = time.strftime("%Y-%m-%dT%H:%M:%S", struct_t)
        except Exception:
            iso_ts = f"{toks[0].replace('.', '-')}T{toks[1]}"

        if mag >= min_mag and _bbox(lat, lon, bbox) and _coastal(lat, lon, place):
            out.append(_mk(lat, lon, mag, place, iso_ts))

    return out
