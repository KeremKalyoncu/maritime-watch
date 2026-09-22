"""İstanbul ve Çanakkale boğazlarının canlı geçiş ve meteorolojik durumunu hesaplar.
Çıktı: web/data/straits.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.model import StraitStatus, now_iso
from src.process.shiptype import (
    DEEP_DRAFT_THRESHOLD_M,
    is_dangerous_cargo,
    is_large_vessel,
)

STRAIT_ZONES = {
    "bosphorus": {
        "id": "bosphorus",
        "name": "İstanbul Boğazı",
        "lat_min": 41.00,
        "lat_max": 41.25,
        "lon_min": 28.98,
        "lon_max": 29.15,
    },
    "dardanelles": {
        "id": "dardanelles",
        "name": "Çanakkale Boğazı",
        "lat_min": 40.05,
        "lat_max": 40.40,
        "lon_min": 26.15,
        "lon_max": 26.70,
    },
}


def evaluate_strait(
    strait_id: str,
    warnings: list[Any],
    vessels_data: dict[str, Any] | None = None,
) -> StraitStatus:
    zone = STRAIT_ZONES[strait_id]
    name = zone["name"]

    # Resmi kapatma, askıya alma veya yoğun sis kontrolü
    is_suspended = False
    suspension_reason = None
    fog_detected = False
    orkoz_detected = False

    for w in warnings:
        area_low = (w.area or "").lower()
        head_low = (w.headline or "").lower()
        if strait_id in area_low or name.lower() in area_low or name.lower() in head_low:
            if "askı" in head_low or "kapat" in head_low or "durdur" in head_low:
                is_suspended = True
                suspension_reason = "Resmi Geçiş Kısıtlaması / Kaza Operasyonu"
                break
            if w.kind in ("fog", "metar") and ("sis" in head_low or "fog" in head_low or "görüş" in head_low):
                is_suspended = True
                fog_detected = True
                suspension_reason = "Yoğun Sis (Görüş < 300m)"
                break
            if "lodos" in head_low or "kıble" in head_low or "orkoz" in head_low:
                orkoz_detected = True

    # Boğaz koridorundaki canlı AIS gemi trafiği ve risk analizi
    in_transit_count = 0
    deep_draft_count = 0
    large_vessel_count = 0
    hazmat_tanker_count = 0
    speeds: list[float] = []

    if vessels_data:
        for _mmsi, v in vessels_data.items():
            track = v.get("track", [])
            if not track:
                continue
            last = track[-1]
            lat, lon = last.get("lat"), last.get("lon")
            if lat is None or lon is None:
                continue
            if zone["lat_min"] <= lat <= zone["lat_max"] and zone["lon_min"] <= lon <= zone["lon_max"]:
                sog = float(last.get("sog") or 0.0)
                if sog >= 0.8:  # underway in strait
                    in_transit_count += 1
                    speeds.append(sog)

                    # Derin draft kontrolü (>= 10.0m)
                    draught = v.get("draught")
                    if draught is not None:
                        try:
                            if float(draught) >= DEEP_DRAFT_THRESHOLD_M:
                                deep_draft_count += 1
                        except (TypeError, ValueError):
                            pass

                    # Büyük boy gemi kontrolü (LOA >= 200m)
                    length = v.get("length")
                    if is_large_vessel(length):
                        large_vessel_count += 1

                    # Tehlikeli yük kontrolü (LNG, Ham Petrol, Kimyasal)
                    type_code = v.get("type_code")
                    name_v = v.get("name", "")
                    if is_dangerous_cargo(type_code, name_v):
                        hazmat_tanker_count += 1

    # Boğaz geçişindeki gemilerin ortalama hızı (gemi yoksa 0.0 kn)
    avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0.0

    high_risk_transit = (large_vessel_count > 0 or hazmat_tanker_count > 0) and (
        orkoz_detected or fog_detected or (in_transit_count >= 5 and avg_speed < 3.5)
    )

    if is_suspended:
        status = "suspended"
        status_tr = "Geçiş Askıya Alındı"
    elif orkoz_detected:
        status = "caution"
        status_tr = "Tedbirli Geçiş"
        suspension_reason = "ORKOZ TEHLİKESİ: Sert Lodos üst akıntıyla çatışıyor, dik kırıcı dalga riski."
    elif high_risk_transit:
        status = "caution"
        status_tr = "Tedbirli Geçiş"
        suspension_reason = f"YÜKSEK RİSKLİ TRANSİT: {large_vessel_count} büyük boy / {hazmat_tanker_count} tehlikeli tanker dar kanalda"
    elif in_transit_count >= 6 and avg_speed < 2.5:
        status = "caution"
        status_tr = "Tedbirli Geçiş"
        suspension_reason = "Trafik Yoğunluğu / Yavaş İlerleme"
    else:
        status = "open"
        status_tr = "Trafik Normal"
        suspension_reason = None

    return StraitStatus(
        id=strait_id,
        name=name,
        status=status,
        status_tr=status_tr,
        reason=suspension_reason,
        active_vessels_in_transit=in_transit_count,
        avg_speed_kn=avg_speed,
        last_update=now_iso(),
        orkoz_detected=orkoz_detected,
        fog_detected=fog_detected,
        deep_draft_count=deep_draft_count,
        large_vessel_count=large_vessel_count,
        hazmat_tanker_count=hazmat_tanker_count,
        high_risk_transit=high_risk_transit,
    )


def render_straits_status(
    store: Any,
    out_file: str | Path | None = None,
    vessels_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_warns = store.active_warnings() if store else []
    bosphorus = evaluate_strait("bosphorus", active_warns, vessels_data)
    dardanelles = evaluate_strait("dardanelles", active_warns, vessels_data)

    payload = {
        "generated": now_iso(),
        "straits": [
            bosphorus.to_dict(),
            dardanelles.to_dict(),
        ],
    }

    if out_file:
        out_path = Path(out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload
