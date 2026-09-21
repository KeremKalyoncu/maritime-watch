from __future__ import annotations

from src.model import Warning
from src.render.straits import evaluate_strait, render_straits_status


def test_strait_normal_open():
    vessels = {
        "101": {"track": [{"lat": 41.10, "lon": 29.05, "sog": 10.2}]},
        "102": {"track": [{"lat": 41.15, "lon": 29.08, "sog": 9.4}]},
    }
    status = evaluate_strait("bosphorus", warnings=[], vessels_data=vessels)
    assert status.id == "bosphorus"
    assert status.status == "open"
    assert status.status_tr == "Trafik Normal"
    assert status.active_vessels_in_transit == 2
    assert status.avg_speed_kn == 9.8
    assert status.reason is None


def test_strait_zero_ships_clean_zero():
    # Gemiler henüz yüklenmediğinde veya boğaz boşken sahte 8.5 kn yazılmamalı, 0.0 olmalı
    status = evaluate_strait("bosphorus", warnings=[], vessels_data={})
    assert status.status == "open"
    assert status.active_vessels_in_transit == 0
    assert status.avg_speed_kn == 0.0
    assert status.reason is None


def test_strait_official_suspension():
    warn = Warning(
        id="kegm-01",
        kind="nav-warning",
        area="İstanbul Boğazı",
        headline="İstanbul Boğazı gemi trafiği kaza nedeniyle çift yönlü askıya alındı",
    )
    status = evaluate_strait("bosphorus", warnings=[warn], vessels_data={})
    assert status.status == "suspended"
    assert status.status_tr == "Geçiş Askıya Alındı"
    assert "Resmi Geçiş Kısıtlaması" in (status.reason or "")


def test_strait_fog_suspension():
    warn = Warning(
        id="metar-ist-01",
        kind="fog",
        area="İstanbul Boğazı",
        headline="Yoğun sis nedeniyle görüş mesafesi 200 metreye düştü",
    )
    status = evaluate_strait("bosphorus", warnings=[warn], vessels_data={})
    assert status.status == "suspended"
    assert "Yoğun Sis" in (status.reason or "")


def test_strait_traffic_jam_caution():
    # 6 veya daha fazla gemi 2.5 kn altında ilerliyorsa tedbirli geçiş
    vessels = {str(i): {"track": [{"lat": 41.05 + (i * 0.02), "lon": 29.04, "sog": 1.8}]} for i in range(6)}
    status = evaluate_strait("bosphorus", warnings=[], vessels_data=vessels)
    assert status.status == "caution"
    assert status.status_tr == "Tedbirli Geçiş"
    assert status.active_vessels_in_transit == 6
    assert status.avg_speed_kn == 1.8


def test_render_straits_file_output(tmp_path):
    out_file = tmp_path / "straits.json"
    payload = render_straits_status(store=None, out_file=out_file, vessels_data={})
    assert out_file.exists()
    assert "generated" in payload
    assert len(payload["straits"]) == 2
    assert payload["straits"][0]["id"] == "bosphorus"
    assert payload["straits"][1]["id"] == "dardanelles"


def test_strait_orkoz_caution():
    warn = Warning(
        id="om-lodos-01",
        kind="marine-weather",
        area="İstanbul Boğazı",
        headline="İstanbul Boğazı şiddetli lodos fırtınası bekleniyor",
    )
    status = evaluate_strait("bosphorus", warnings=[warn], vessels_data={})
    assert status.status == "caution"
    assert status.status_tr == "Tedbirli Geçiş"
    assert status.orkoz_detected is True
    assert "ORKOZ TEHLİKESİ" in (status.reason or "")
