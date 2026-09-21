"""Marine physics and traditional nautical direction calculations.

Zero external dependencies: 16-wind Turkish compass rose, wave steepness
(period vs height) and coastal vulnerability vectors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

# 16 geleneksel Türk denizci pusula yönü (0° / 360° Yıldız = Kuzey)
COMPASS_POINTS_TR = [
    "Yıldız",  # 0°    N
    "Yıldız-Poyraz",  # 22.5° NNE
    "Poyraz",  # 45°   NE
    "Gündoğusu-Poyraz",  # 67.5° ENE
    "Gündoğusu",  # 90°   E
    "Gündoğusu-Keşişleme",  # 112.5° ESE
    "Keşişleme",  # 135°  SE
    "Kıble-Keşişleme",  # 157.5° SSE
    "Kıble",  # 180°  S
    "Kıble-Lodos",  # 202.5° SSW
    "Lodos",  # 225°  SW
    "Batı-Lodos",  # 247.5° WSW
    "Günbatısı",  # 270°  W
    "Batı-Karayel",  # 292.5° WNW
    "Karayel",  # 315°  NW
    "Yıldız-Karayel",  # 337.5° NNW
]

COMPASS_POINTS_EN = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
]


class WindSector(str, Enum):
    NORTHERN = "northern"  # Karayel, Yıldız, Poyraz
    EASTERN = "eastern"  # Gündoğusu, Keşişleme
    SOUTHERLY = "southerly"  # Kıble, Lodos (Marmara ve Ege'de en tehlikeli)
    WESTERN = "western"  # Günbatısı


def degree_to_compass_tr(deg: float | None) -> str:
    """Map a 0-360 degree wind angle to the traditional Turkish 16-point compass name.

    0° = Yıldız (Kuzey), 45° = Poyraz (Kuzeydoğu), 135° = Keşişleme (Güneydoğu),
    180° = Kıble (Güney), 225° = Lodos (Güneybatı), 315° = Karayel (Kuzeybatı).
    """
    if deg is None or not isinstance(deg, (int, float)) or math.isnan(deg):
        return "Belirsiz"
    normalized = (float(deg) % 360.0 + 360.0) % 360.0
    idx = int((normalized + 11.25) / 22.5) % 16
    return COMPASS_POINTS_TR[idx]


def degree_to_compass_en(deg: float | None) -> str:
    """Map a 0-360 degree wind angle to standard international 16-point cardinal string."""
    if deg is None or not isinstance(deg, (int, float)) or math.isnan(deg):
        return "N/A"
    normalized = (float(deg) % 360.0 + 360.0) % 360.0
    idx = int((normalized + 11.25) / 22.5) % 16
    return COMPASS_POINTS_EN[idx]


def is_southerly_hazard(deg: float | None, gust_kn: float = 0.0) -> bool:
    """True if wind is blowing from the South/Southwest quadrant (157.5° to 247.5°).

    Lodos and Kıble are notorious in the Sea of Marmara, the Turkish Straits,
    and Northern Aegean for creating steep opposing swells and breaking waves against southern harbours.
    """
    if deg is None or not isinstance(deg, (int, float)) or math.isnan(deg):
        return False
    normalized = (float(deg) % 360.0 + 360.0) % 360.0
    # Kıble-Keşişleme (157.5°) through Batı-Lodos (247.5°)
    return 157.5 <= normalized <= 247.5


@dataclass(frozen=True)
class WaveSteepness:
    is_steep: bool
    steepness_ratio: float
    wavelength_m: float
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_steep": self.is_steep,
            "steepness_ratio": round(self.steepness_ratio, 4),
            "wavelength_m": round(self.wavelength_m, 1),
            "reason": self.reason,
        }


def analyze_wave_steepness(
    height_m: float | None,
    period_s: float | None,
) -> WaveSteepness:
    """Calculate wave steepness (H / L) and identify dangerous short breaking waves.

    In deep/coastal transition water:
    Wave Length L ~= 1.56 * (T ^ 2) in meters.
    Wave Steepness = Height / Length (H / L).

    When H/L > 0.065 or when period < 4.5s with wave height >= 0.7m,
    waves are short, square and breaking, creating severe capsizing risks for small vessels (<8m).
    """
    if (
        height_m is None
        or period_s is None
        or height_m <= 0.0
        or period_s <= 0.0
        or math.isnan(height_m)
        or math.isnan(period_s)
    ):
        return WaveSteepness(is_steep=False, steepness_ratio=0.0, wavelength_m=0.0, reason=None)

    wavelength = 1.56 * (period_s**2)
    ratio = height_m / wavelength if wavelength > 0 else 0.0

    is_steep = (ratio >= 0.065) or (period_s < 4.5 and height_m >= 0.7)
    reason = None
    if is_steep:
        reason = f"Dik ve çırpıntılı kırıcı dalga (Periyot {period_s:.1f}s / Boy {height_m:.1f}m)"

    return WaveSteepness(
        is_steep=is_steep,
        steepness_ratio=ratio,
        wavelength_m=wavelength,
        reason=reason,
    )
