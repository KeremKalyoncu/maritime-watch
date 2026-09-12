"""Small craft and artisanal fisherman marine safety index (Go / No-Go).
Evaluates wave height, sustained wind, wind gusts and official meteorological
warnings to calculate a 0-100 safety score and actionable recommendations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.model import MarineSafetyRating, now_iso

W_WAVE = 25.0   # penalty points per meter above 0.6m
W_WIND = 1.5    # penalty points per knot above 10 kn
W_GUST = 1.2    # penalty points per knot above 15 kn
ALARM_PENALTY = 50.0  # deduction if an active official storm/gale warning exists


def calculate_safety_score(
    wave_m: float | None,
    wind_kn: float,
    gust_kn: float,
    has_storm_warning: bool = False,
) -> int:
    """Calculate an integer safety score in [0, 100]."""
    penalty = 0.0

    # Wave penalty (if wave model available)
    if wave_m is not None:
        effective_wave = max(0.0, float(wave_m) - 0.6)
        penalty += W_WAVE * effective_wave
    else:
        # In sheltered bays where wave model is null, add slight caution penalty if wind is high
        if wind_kn > 15.0:
            penalty += 10.0

    # Wind penalty
    effective_wind = max(0.0, float(wind_kn) - 10.0)
    penalty += W_WIND * effective_wind

    # Gust penalty
    effective_gust = max(0.0, float(gust_kn) - 15.0)
    penalty += W_GUST * effective_gust

    # Official warning penalty
    if has_storm_warning:
        penalty += ALARM_PENALTY

    raw_score = 100.0 - penalty
    clamped = max(0, min(100, int(round(raw_score))))
    return clamped


def score_to_status(score: int) -> str:
    """Determine status rating based on score."""
    if score >= 75:
        return "good"
    if score >= 45:
        return "caution"
    return "danger"


def get_recommendations(status: str) -> tuple[str, str]:
    """Return Turkish and English recommendation text based on status."""
    if status == "good":
        return (
            "Hava ve deniz koşulları elverişli. Küçük tekneler ve amatör balıkçılar için uygundur.",
            "Weather and sea conditions favorable. Suitable for small craft and artisanal fishing.",
        )
    if status == "caution":
        return (
            "Çırpıntılı deniz, donanımlı tekneler seyredebilir. Can yeleği takın ve hava raporunu takip edin.",
            "Choppy seas, equipped vessels may sail. Wear lifejackets and monitor weather updates.",
        )
    return (
        "Denize çıkmayın! Fırtına hamlesi ve dik dalgalar küçük tekneler için alabora riski taşır.",
        "Do not sail! Severe gusts and steep waves pose capsize risks for small craft.",
    )


def calculate_safety_rating(
    area: str,
    wave_m: float | None,
    wind_kn: float,
    gust_kn: float,
    has_storm_warning: bool = False,
) -> MarineSafetyRating:
    """Produce a full MarineSafetyRating model for a coastal region."""
    score = calculate_safety_score(
        wave_m=wave_m,
        wind_kn=wind_kn,
        gust_kn=gust_kn,
        has_storm_warning=has_storm_warning,
    )
    status = score_to_status(score)
    rec_tr, rec_en = get_recommendations(status)

    return MarineSafetyRating(
        area=area,
        score=score,
        status=status,
        wave_m=round(wave_m, 2) if wave_m is not None else None,
        wind_kn=round(wind_kn, 1),
        gust_kn=round(gust_kn, 1),
        recommendation_tr=rec_tr,
        recommendation_en=rec_en,
        last_update=now_iso(),
    )


def evaluate_all_areas(
    points: list[dict[str, Any]],
    storm_areas: set[str] | None = None,
) -> list[MarineSafetyRating]:
    """Given a list of weather point dictionaries, compute ratings for all areas."""
    storm_areas = storm_areas or set()
    ratings: list[MarineSafetyRating] = []

    for pt in points:
        name = pt.get("name", "Bilinmeyen Bölge")
        wave = pt.get("wave_m")
        wind = float(pt.get("wind_kn") or 0.0)
        gust = float(pt.get("gust_kn") or wind)
        has_warn = (name in storm_areas) or any(s in name for s in storm_areas)

        rating = calculate_safety_rating(
            area=name,
            wave_m=wave,
            wind_kn=wind,
            gust_kn=gust,
            has_storm_warning=has_warn,
        )
        ratings.append(rating)

    return ratings


def render_safety_index(
    points: list[dict[str, Any]],
    storm_areas: set[str] | None = None,
    out_file: str | Path | None = None,
) -> dict[str, Any]:
    ratings = evaluate_all_areas(points, storm_areas)
    payload = {
        "generated": now_iso(),
        "ratings": [r.to_dict() for r in ratings],
    }
    if out_file:
        import json
        from pathlib import Path
        out_path = Path(out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
