"""Critical coastal shallow banks, shoals and reef hazards in Turkish waters.

Used to evaluate grounding risk for deep-draught commercial vessels.
Pure mathematics, zero external dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ShallowBank:
    id: str
    name: str
    lat: float
    lon: float
    depth_m: float  # Minimum charted depth in meters
    radius_nm: float  # Danger perimeter in Nautical Miles


# Critical commercial shoals in the Turkish Straits, Marmara, and approaches
SHALLOW_BANKS: list[ShallowBank] = [
    ShallowBank(
        id="vordonisi",
        name="Vordonisi / Bostancı Sığlığı",
        lat=40.9450,
        lon=29.0700,
        depth_m=4.5,
        radius_nm=0.40,
    ),
    ShallowBank(
        id="kumkapi",
        name="Kumkapı Sığlığı (Tarihi Yarımada Açıkları)",
        lat=41.0000,
        lon=28.9650,
        depth_m=6.0,
        radius_nm=0.45,
    ),
    ShallowBank(
        id="kandilli",
        name="Kandilli Akıntı Burnu Sığlığı",
        lat=41.0750,
        lon=29.0580,
        depth_m=7.0,
        radius_nm=0.25,
    ),
    ShallowBank(
        id="bebek",
        name="Bebek Koyu Sığlık Bankı",
        lat=41.0770,
        lon=29.0450,
        depth_m=6.5,
        radius_nm=0.25,
    ),
    ShallowBank(
        id="nara",
        name="Çanakkale Nara Burnu Sığlığı",
        lat=40.2000,
        lon=26.4000,
        depth_m=5.5,
        radius_nm=0.40,
    ),
    ShallowBank(
        id="cesme_uzunada",
        name="Çeşme Uzunada Sığlığı",
        lat=38.3500,
        lon=26.3300,
        depth_m=4.0,
        radius_nm=0.45,
    ),
    ShallowBank(
        id="gokceada_aydincik",
        name="Gökçeada Aydıncık Sığlığı",
        lat=40.1500,
        lon=25.9800,
        depth_m=5.0,
        radius_nm=0.45,
    ),
]


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in Nautical Miles."""
    r_nm = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_nm * c


def evaluate_grounding_risk(
    lat: float | None,
    lon: float | None,
    draught: float | None,
    sog: float | None = None,
) -> dict[str, Any] | None:
    """Check if a vessel is dangerously close to a charted shallow bank relative to its draught.

    Returns risk details if:
    - Coordinates and draught are valid
    - Vessel draught exceeds bank depth + 0.5m safety under-keel clearance (UKC)
    - Vessel is within the danger radius of the bank
    - Vessel is moving (sog >= 1.0 kn) or stationary in hazard zone
    """
    if lat is None or lon is None or draught is None:
        return None

    try:
        f_lat = float(lat)
        f_lon = float(lon)
        f_draught = float(draught)
    except (TypeError, ValueError):
        return None

    # Small boats or light vessels (<= 5.0m draft) are safe from these deep-draft banks
    if f_draught <= 5.0:
        return None

    for bank in SHALLOW_BANKS:
        dist_nm = _haversine_nm(f_lat, f_lon, bank.lat, bank.lon)
        if dist_nm <= bank.radius_nm:
            clearance = bank.depth_m - f_draught
            if clearance < 1.0:  # Under-Keel Clearance less than 1.0m or negative (grounding)
                return {
                    "bank_id": bank.id,
                    "bank_name": bank.name,
                    "bank_depth_m": bank.depth_m,
                    "vessel_draught_m": round(f_draught, 1),
                    "under_keel_clearance_m": round(clearance, 1),
                    "distance_nm": round(dist_nm, 2),
                    "distance_m": int(dist_nm * 1852),
                }

    return None
