"""AIS ship-type code -> broad category -> anomaly tuning.

A fishing boat or a yacht drifting/loitering is normal; a cargo ship or tanker
stopping mid-sea is not. The category decides whether the speed-drop rule fires
and how sensitive it is.
"""

from __future__ import annotations

CATEGORY_TR = {
    "fishing": "balıkçı teknesi",
    "pleasure": "gezi teknesi / yelkenli",
    "passenger": "yolcu gemisi / feribot",
    "cargo": "kuru yük gemisi",
    "tanker": "tanker",
    "tug": "römorkör / hizmet",
    "sar": "arama kurtarma",
    "other": "diğer",
    "unknown": "bilinmiyor",
}


def category(type_code) -> str:
    try:
        t = int(type_code)
    except (TypeError, ValueError):
        return "unknown"
    if t == 30:
        return "fishing"
    if t in (36, 37):
        return "pleasure"
    if 60 <= t <= 69:
        return "passenger"
    if 70 <= t <= 79:
        return "cargo"
    if 80 <= t <= 89:
        return "tanker"
    if t in (31, 32, 52):
        return "tug"
    if t == 51:
        return "sar"
    return "other"


# speed_drop: does an unexplained stop count as an anomaly for this category?
# sensitive: flag it earlier (lower "was under way" bar) and as a stronger signal
_PROFILE = {
    "fishing": {"speed_drop": False, "sensitive": False},
    "pleasure": {"speed_drop": False, "sensitive": False},
    "sar": {"speed_drop": False, "sensitive": False},
    "tug": {"speed_drop": False, "sensitive": False},
    "passenger": {"speed_drop": True, "sensitive": False},
    "cargo": {"speed_drop": True, "sensitive": True},
    "tanker": {"speed_drop": True, "sensitive": True},
    "other": {"speed_drop": True, "sensitive": False},
    "unknown": {"speed_drop": True, "sensitive": False},
}


def profile(type_code) -> dict:
    return _PROFILE[category(type_code)]


# Maritime regulatory thresholds for Turkish Straits and coastal navigation
LARGE_VESSEL_THRESHOLD_M: float = 200.0  # Turkish Straits Regulations (VTS): escort/pilot rules apply
DEEP_DRAFT_THRESHOLD_M: float = 10.0  # Commercial deep-draught navigation limit

HAZARD_TR = {
    "lng_lpg": "LNG / LPG Gaz Tankeri (Yüksek Risk)",
    "chemical": "Kimyasal Madde Tankeri (Tehlikeli Yük)",
    "crude_oil": "Ham Petrol Tankeri (Büyük Çevre Riski)",
    "dangerous_goods": "Tehlikeli Madde Taşıyan Yük Gemisi",
    "none": "Standart Ticari / Tehlikesiz",
}


def hazard_category(type_code: int | str | None, name: str = "") -> str:
    """Classify cargo danger category based on ITU-R M.1371 type code and vessel naming cues."""
    try:
        t = int(type_code) if type_code is not None else None
    except (TypeError, ValueError):
        t = None

    u_name = (name or "").upper()
    if any(k in u_name for k in (" LNG ", " LPG ", "GAS ", "ETHANE ", "METHANE ")):
        return "lng_lpg"

    if t is None:
        return "none"

    if t == 84:
        return "lng_lpg"
    if t == 82:
        return "chemical"
    if t in (81, 83):
        return "crude_oil"
    if 80 <= t <= 89:
        return "crude_oil"
    if 71 <= t <= 74:
        return "dangerous_goods"

    return "none"


def is_dangerous_cargo(type_code: int | str | None, name: str = "") -> bool:
    """True if vessel carries hazardous substances, petroleum, or gas cargo."""
    return hazard_category(type_code, name) != "none"


def is_large_vessel(length: float | int | None) -> bool:
    """True if vessel length overall (LOA) meets or exceeds Turkish Straits 200m threshold."""
    if length is None:
        return False
    try:
        return float(length) >= LARGE_VESSEL_THRESHOLD_M
    except (TypeError, ValueError):
        return False
