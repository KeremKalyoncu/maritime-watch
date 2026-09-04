"""AIS ship-type code -> broad category -> anomaly tuning.

A fishing boat or a yacht drifting/loitering is normal; a cargo ship or tanker
stopping mid-sea is not. The category decides whether the speed-drop rule fires
and how sensitive it is.
"""

from __future__ import annotations

CATEGORY_TR = {
    "fishing": "balıkçı teknesi", "pleasure": "gezi teknesi / yelkenli",
    "passenger": "yolcu gemisi / feribot", "cargo": "kuru yük gemisi",
    "tanker": "tanker", "tug": "römorkör / hizmet", "sar": "arama kurtarma",
    "other": "diğer", "unknown": "bilinmiyor",
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
    "fishing":   {"speed_drop": False, "sensitive": False},
    "pleasure":  {"speed_drop": False, "sensitive": False},
    "sar":       {"speed_drop": False, "sensitive": False},
    "tug":       {"speed_drop": False, "sensitive": False},
    "passenger": {"speed_drop": True,  "sensitive": False},
    "cargo":     {"speed_drop": True,  "sensitive": True},
    "tanker":    {"speed_drop": True,  "sensitive": True},
    "other":     {"speed_drop": True,  "sensitive": False},
    "unknown":   {"speed_drop": True,  "sensitive": False},
}


def profile(type_code) -> dict:
    return _PROFILE[category(type_code)]
