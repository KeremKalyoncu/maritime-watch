from __future__ import annotations

import math
from src.process.marine_physics import (
    analyze_wave_steepness,
    degree_to_compass_en,
    degree_to_compass_tr,
    is_southerly_hazard,
)


def test_degree_to_compass_tr_cardinal():
    # 0° / 360° = Yıldız
    assert degree_to_compass_tr(0) == "Yıldız"
    assert degree_to_compass_tr(360) == "Yıldız"
    assert degree_to_compass_tr(720) == "Yıldız"
    assert degree_to_compass_tr(-360) == "Yıldız"

    # Main cardinal points
    assert degree_to_compass_tr(45) == "Poyraz"
    assert degree_to_compass_tr(90) == "Gündoğusu"
    assert degree_to_compass_tr(135) == "Keşişleme"
    assert degree_to_compass_tr(180) == "Kıble"
    assert degree_to_compass_tr(225) == "Lodos"
    assert degree_to_compass_tr(270) == "Günbatısı"
    assert degree_to_compass_tr(315) == "Karayel"


def test_degree_to_compass_tr_boundaries():
    # 22.5° sector boundaries (center +- 11.25°)
    # Yıldız is [-11.25, 11.25] -> [348.75, 11.25]
    assert degree_to_compass_tr(11.2) == "Yıldız"
    assert degree_to_compass_tr(11.3) == "Yıldız-Poyraz"

    # Poyraz is 45° -> [33.75, 56.25]
    assert degree_to_compass_tr(34.0) == "Poyraz"
    assert degree_to_compass_tr(56.0) == "Poyraz"

    # Lodos is 225° -> [213.75, 236.25]
    assert degree_to_compass_tr(224.0) == "Lodos"
    assert degree_to_compass_tr(226.0) == "Lodos"


def test_degree_to_compass_tr_null_edge():
    assert degree_to_compass_tr(None) == "Belirsiz"
    assert degree_to_compass_tr(float("nan")) == "Belirsiz"


def test_degree_to_compass_en():
    assert degree_to_compass_en(0) == "N"
    assert degree_to_compass_en(45) == "NE"
    assert degree_to_compass_en(225) == "SW"
    assert degree_to_compass_en(315) == "NW"
    assert degree_to_compass_en(None) == "N/A"


def test_is_southerly_hazard():
    # Lodos (225°), Kıble (180°) are southerly
    assert is_southerly_hazard(225) is True
    assert is_southerly_hazard(180) is True
    assert is_southerly_hazard(202.5) is True

    # Poyraz (45°), Karayel (315°), Yıldız (0°) are not southerly
    assert is_southerly_hazard(45) is False
    assert is_southerly_hazard(315) is False
    assert is_southerly_hazard(0) is False
    assert is_southerly_hazard(None) is False


def test_analyze_wave_steepness_choppy():
    # Short period (3.2s) with high wave (1.2m) -> dangerous steep wave
    res = analyze_wave_steepness(1.2, 3.2)
    assert res.is_steep is True
    assert res.steepness_ratio > 0.065
    assert "Dik ve çırpıntılı" in (res.reason or "")


def test_analyze_wave_steepness_swell():
    # Long period swell (8.5s) with 1.2m wave -> gentle swell, not steep
    res = analyze_wave_steepness(1.2, 8.5)
    assert res.is_steep is False
    assert res.steepness_ratio < 0.05
    assert res.reason is None


def test_analyze_wave_steepness_null_and_zero():
    assert analyze_wave_steepness(None, 4.0).is_steep is False
    assert analyze_wave_steepness(1.0, None).is_steep is False
    assert analyze_wave_steepness(0.0, 4.0).is_steep is False
    assert analyze_wave_steepness(1.0, 0.0).is_steep is False
