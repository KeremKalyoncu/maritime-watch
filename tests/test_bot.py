"""Per-chat subscriptions. A broadcast channel sends a Marmara fisherman twelve
sea areas they do not care about."""

import json
from datetime import UTC

import pytest

from src.alert.bot import Bot, Subscribers


@pytest.fixture
def bot(cfg, tmp_path):
    cfg["secrets"] = {"telegram_token": "", "telegram_chat_id": "", "aisstream_key": ""}
    return Bot(cfg)


def _msg(chat, text):
    return {"update_id": 1, "message": {"chat": {"id": chat}, "text": text}}


def _cb(chat, data, mid=7):
    return {"update_id": 2, "callback_query": {"id": "q", "data": data,
                                               "message": {"chat": {"id": chat}, "message_id": mid}}}


def test_start_creates_a_subscriber_with_safe_defaults(bot):
    bot.handle(_msg(42, "/start"))
    s = bot.subs.data["42"]
    assert s["active"] is True
    assert s["areas"] == []            # empty means every area
    assert s["boat"] == "small"        # the audience the channel claims to serve


def test_area_toggle_is_a_toggle(bot):
    bot.handle(_msg(42, "/start"))
    first = bot.areas[0]
    bot.handle(_cb(42, "area:0"))
    assert bot.subs.data["42"]["areas"] == [first]
    bot.handle(_cb(42, "area:0"))
    assert bot.subs.data["42"]["areas"] == []


def test_choosing_all_areas_clears_the_filter(bot):
    bot.handle(_msg(42, "/start"))
    bot.handle(_cb(42, "area:1"))
    bot.handle(_cb(42, "area:all"))
    assert bot.subs.data["42"]["areas"] == []


def test_boat_class_must_be_one_we_know(bot):
    bot.handle(_msg(42, "/start"))
    bot.handle(_cb(42, "boat:large"))
    assert bot.subs.data["42"]["boat"] == "large"
    bot.handle(_cb(42, "boat:submarine"))
    assert bot.subs.data["42"]["boat"] == "large"      # unchanged


def test_stop_keeps_the_settings_but_stops_the_messages(bot):
    bot.handle(_msg(42, "/start"))
    bot.handle(_cb(42, "area:0"))
    bot.handle(_msg(42, "/dur"))
    assert bot.subs.data["42"]["active"] is False
    assert bot.subs.data["42"]["areas"]                # remembered for /start
    assert bot.subs.active() == []


def test_unknown_command_gets_the_help_not_silence(bot):
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)
    bot.handle(_msg(42, "/kahve"))
    assert sent and "/bolge" in sent[0]


def test_settings_are_written_and_read_back(bot, tmp_path):
    bot.handle(_msg(42, "/start"))
    bot.handle(_cb(42, "boat:medium"))
    bot.subs.save()
    again = Subscribers(str(bot.subs.path))
    assert again.data["42"]["boat"] == "medium"
    assert json.loads(bot.subs.path.read_text("utf-8"))["chats"]["42"]["boat"] == "medium"


def test_offset_survives_a_restart_so_commands_do_not_replay(bot):
    bot.subs.offset = 991
    bot.subs.save()
    assert Subscribers(str(bot.subs.path)).offset == 991


def test_subscriber_file_is_git_ignored():
    """Chat ids identify people and this repo is public."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    assert "data/subscribers.json" in (root / ".gitignore").read_text("utf-8")


def test_a_subscriber_only_gets_the_areas_they_chose(cfg, tmp_path):
    from src.alert.telegram import Notifier
    from src.render.outlook import render_outlook

    cfg = dict(cfg)
    cfg["_root"] = str(tmp_path)
    cfg["secrets"] = {"telegram_token": "", "telegram_chat_id": "", "aisstream_key": ""}
    times = [f"2026-09-10T{h:02d}:00" for h in range(13)]
    pts = [{"name": n, "lat": 41.0, "lon": 29.0, "times": times,
            "gusts": [26] * 12, "waves": [0.3] * 12}
           for n in ("Marmara Denizi", "Antalya Körfezi")]
    assert render_outlook(cfg, tmp_path / "web" / "data" / "outlook.json", points=pts)
    txt = Notifier(cfg).outlook_text_for(cfg, {"areas": ["Marmara Denizi"], "boat": "small"})
    assert "MARMARA DENİZİ" in txt
    assert "Antalya" not in txt


def test_boat_class_changes_the_verdict_for_the_same_weather(cfg, tmp_path):
    from src.alert.telegram import Notifier
    from src.render.outlook import render_outlook

    cfg = dict(cfg)
    cfg["_root"] = str(tmp_path)
    cfg["secrets"] = {"telegram_token": "", "telegram_chat_id": "", "aisstream_key": ""}
    times = [f"2026-09-10T{h:02d}:00" for h in range(13)]
    pts = [{"name": "Marmara Denizi", "lat": 41.0, "lon": 29.0, "times": times,
            "gusts": [25] * 12, "waves": [0.4] * 12}]
    assert render_outlook(cfg, tmp_path / "web" / "data" / "outlook.json", points=pts)
    n = Notifier(cfg)
    assert "ÇIKMA" in n.outlook_text_for(cfg, {"areas": [], "boat": "small"})
    assert "ÇIKMA" not in n.outlook_text_for(cfg, {"areas": [], "boat": "large"})


def test_location_query_neredeyim(bot):
    """TC-BOT-01: Canlı GPS Konum Sorgusu (/neredeyim)."""
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)

    loc_msg = {
        "update_id": 10,
        "message": {
            "chat": {"id": 99},
            "location": {"latitude": 38.3245, "longitude": 26.3012}
        }
    }
    bot.handle(loc_msg)
    assert len(sent) == 1
    resp = sent[0]
    assert "Çeşme Limanı" in resp
    assert "158" in resp
    assert "NM" in resp
    assert "°" in resp
    assert "Sefer skoru" in resp
    assert "85/100" not in resp
    assert "veri yok" in resp.lower() or "derlenmedi" in resp.lower()

    # Also test via text command with coordinates
    sent.clear()
    bot.handle(_msg(99, "/neredeyim 38.3245 26.3012"))
    assert len(sent) == 1
    assert "Çeşme Limanı" in sent[0]
    assert "158" in sent[0]


def test_subscribe_valid_region(bot):
    """TC-BOT-02: Bölge Aboneliği Ekleme (/abone [bolge])."""
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)

    bot.handle(_msg(42, "/abone Marmara Denizi"))
    assert len(sent) == 1
    assert "Marmara Denizi" in sent[0]
    assert "abone oldunuz" in sent[0]
    assert "Marmara Denizi" in bot.subs.data["42"]["areas"]

    # Verify synchronization with data/bot_subscribers.json
    bot_sub_file = bot.subs.path.parent / "bot_subscribers.json"
    assert bot_sub_file.exists()
    b_data = json.loads(bot_sub_file.read_text("utf-8"))
    assert "42" in b_data.get("Marmara Denizi", [])


def test_unsubscribe_cancels_subscription(bot):
    """TC-BOT-03: Abonelik İptali (/abone iptal)."""
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)

    bot.handle(_msg(42, "/abone Marmara Denizi"))
    sent.clear()
    bot.handle(_msg(42, "/abone iptal"))
    assert len(sent) == 1
    assert "Aboneliğiniz iptal edildi" in sent[0]
    assert bot.subs.data["42"]["areas"] == []

    # Verify removal from data/bot_subscribers.json
    bot_sub_file = bot.subs.path.parent / "bot_subscribers.json"
    b_data = json.loads(bot_sub_file.read_text("utf-8"))
    assert "42" not in b_data.get("Marmara Denizi", [])


def test_subscribe_invalid_region_rejected(bot):
    """TC-BOT-04: Geçersiz Bölge Adı Reddi."""
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)

    bot.handle(_msg(42, "/abone ankara"))
    assert len(sent) == 1
    assert "Geçersiz bölge adı" in sent[0]
    assert "Marmara Denizi" in sent[0]
    assert "ankara" not in bot.subs.data["42"]["areas"]


def test_expired_location_rejected(bot):
    """TC-BOT-05: Zaman Aşımına Uğramış Konum Paylaşımı."""
    import time
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)

    old_time = time.time() - 1200  # 20 minutes ago (> 900s)
    loc_msg = {
        "update_id": 11,
        "message": {
            "chat": {"id": 99},
            "date": old_time,
            "location": {"latitude": 38.3245, "longitude": 26.3012}
        }
    }
    bot.handle(loc_msg)
    assert len(sent) == 1
    assert "Konumunuz güncel değil, lütfen canlı konum paylaşın" in sent[0]


def test_mayday_command_with_and_without_location(bot):
    """Test /mayday generates valid Turkish VHF Ch 16 distress script."""
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)

    # 1. Without previous location
    bot.handle(_msg(42, "/mayday"))
    assert len(sent) == 1
    assert "MAYDAY, MAYDAY, MAYDAY" in sent[0]
    assert "158" in sent[0]
    assert "VHF" in sent[0]

    # 2. With known location
    bot.handle(_msg(42, "/neredeyim 38.3245 26.3012"))
    sent.clear()
    bot.handle(_msg(42, "/mayday"))
    assert len(sent) == 1
    assert "Çeşme Limanı" in sent[0]
    assert "38.3245°K" in sent[0]


def test_straits_command(bot):
    """Test /bogaz returns Turkish Straits status."""
    from pathlib import Path
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)

    straits_file = Path(bot.cfg["_root"]) / "web" / "data" / "straits.json"
    straits_file.parent.mkdir(parents=True, exist_ok=True)
    straits_file.write_text(json.dumps({
        "straits": [
            {"name": "İstanbul Boğazı", "status": "suspended", "status_tr": "Askıya Alındı", "reason": "Yoğun Sis", "active_vessels_in_transit": 2, "avg_speed_kn": 1.5},
            {"name": "Çanakkale Boğazı", "status": "open", "status_tr": "Açık", "reason": None, "active_vessels_in_transit": 12, "avg_speed_kn": 9.2}
        ]
    }, ensure_ascii=False), encoding="utf-8")

    bot.handle(_msg(42, "/bogaz"))
    assert len(sent) == 1
    assert "İstanbul Boğazı" in sent[0]
    assert "Çanakkale Boğazı" in sent[0]
    assert "Yoğun Sis" in sent[0]


def test_fisherman_command(bot):
    """Test /balikci returns today's hour windows, not only a score."""
    from pathlib import Path
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)

    data_dir = Path(bot.cfg["_root"]) / "web" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_dir.joinpath("outlook.json").write_text(json.dumps({
        "schema_version": 1,
        "generated": "2026-09-19T05:00:00Z",
        "hours": 18,
        "tz_offset_hours": 3,
        "question": "today",
        "classes": {
            "small": {
                "label": "küçük tekne (8 m ve altı)",
                "limits": {"label": "küçük tekne", "gust_kn": 22, "wave_m": 1.25},
                "areas": [{
                    "name": "Marmara Denizi",
                    "lat": 40.7, "lon": 28.2,
                    "windows": [
                        {"start": "06:00", "end": "12:00", "level": "ok", "gust_kn": 10, "wave_m": 0.4},
                        {"start": "12:00", "end": "18:00", "level": "danger", "gust_kn": 26, "wave_m": 0.5},
                    ],
                    "max_gust": 26, "max_wave": 0.5,
                    "first_danger_start": "12:00",
                    "return_by": "12:00",
                    "worst": "danger",
                }],
            },
            "medium": {"label": "orta", "limits": {"gust_kn": 28, "wave_m": 2.0}, "areas": []},
            "large": {"label": "büyük", "limits": {"gust_kn": 34, "wave_m": 3.0}, "areas": []},
        },
    }, ensure_ascii=False), encoding="utf-8")
    data_dir.joinpath("safety_index.json").write_text(json.dumps({
        "ratings": [
            {"area": "Marmara Denizi", "score": 88, "status": "good", "wave_m": 0.5,
             "wind_kn": 10, "gust_kn": 14, "recommendation_tr": "ok", "data_quality": "ok"}
        ]
    }, ensure_ascii=False), encoding="utf-8")

    bot.handle(_msg(42, "/balikci Marmara"))
    assert len(sent) == 1
    assert "Marmara Denizi" in sent[0]
    assert "Bugün" in sent[0]
    assert "12:00" in sent[0]
    assert "Limana dönüş" in sent[0]
    assert "88/100" in sent[0]
    assert "Şimdi" in sent[0]


def test_kazalar_command(bot):
    """Test /kazalar accepts wrapped {incidents: []} shape."""
    from pathlib import Path
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)

    inc_file = Path(bot.cfg["_root"]) / "web" / "data" / "incidents.json"
    inc_file.parent.mkdir(parents=True, exist_ok=True)
    inc_file.write_text(json.dumps({
        "incidents": [
            {"type": "sinking", "type_tr": "batma", "area": "Şile", "status": "confirmed",
             "vessel": {"name": "Koster-1"}, "summary": "Gemi battı"}
        ]
    }, ensure_ascii=False), encoding="utf-8")

    bot.handle(_msg(42, "/kazalar"))
    assert len(sent) == 1
    assert "GÜNCEL DENİZ OLAYLARI" in sent[0]
    assert "Şile" in sent[0]


def test_kazalar_accepts_top_level_array(bot):
    from pathlib import Path
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)
    inc_file = Path(bot.cfg["_root"]) / "web" / "data" / "incidents.json"
    inc_file.parent.mkdir(parents=True, exist_ok=True)
    inc_file.write_text(json.dumps([
        {"type": "rescue", "type_tr": "kurtarma", "area": "Bodrum", "status": "confirmed",
         "vessel": {"name": "X"}, "summary": "SG operasyonu"}
    ], ensure_ascii=False), encoding="utf-8")
    bot.handle(_msg(42, "/kazalar"))
    assert "Bodrum" in sent[0]


def test_reply_keyboard_maps_bugun_to_balikci():
    from src.alert.bot import _inline_home_menu, _keyboard_command, _reply_keyboard
    assert _keyboard_command("🎣 Bugün") == "balikci"
    assert _keyboard_command("🌊 Durum") == "durum"
    assert _keyboard_command("🚢 Boğaz") == "bogaz"
    kb = json.loads(_reply_keyboard())
    assert kb["resize_keyboard"] is True
    assert any(btn["text"] == "🎣 Bugün" for row in kb["keyboard"] for btn in row)
    inline = json.loads(_inline_home_menu())
    assert any(b.get("callback_data") == "menu:balikci"
               for row in inline["inline_keyboard"] for b in row)


def test_start_attaches_menus(bot):
    sent = []
    markups = []

    def capture(chat, text, markup=None, dry=True):
        sent.append(text)
        markups.append(markup)

    bot.send = capture
    bot.handle(_msg(99, "/start"))
    assert any("Hoş geldin" in t for t in sent)
    assert any(m and "keyboard" in m for m in markups if m)
    assert any(m and "inline_keyboard" in m for m in markups if m)


def test_keyboard_tap_runs_balikci(bot):
    from pathlib import Path
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)
    data_dir = Path(bot.cfg["_root"]) / "web" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_dir.joinpath("outlook.json").write_text(json.dumps({
        "schema_version": 1, "classes": {
            "small": {"label": "küçük", "limits": {}, "areas": [{
                "name": "Marmara Denizi",
                "windows": [{"start": "08:00", "end": "16:00", "level": "ok",
                             "gust_kn": 10, "wave_m": 0.4}],
                "return_by": None, "worst": "ok",
            }]},
            "medium": {"label": "m", "limits": {}, "areas": []},
            "large": {"label": "l", "limits": {}, "areas": []},
        },
    }, ensure_ascii=False), encoding="utf-8")
    bot.handle(_msg(42, "🎣 Bugün"))
    assert sent and "Bugün" in sent[0]


def test_neredeyim_never_invents_eighty_five(bot):
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)
    bot.handle(_msg(42, "/neredeyim 38.3245 26.3012"))
    assert sent
    assert "85/100" not in sent[0]
    assert "Elverişli" not in sent[0] or "veri yok" in sent[0].lower()


def test_balikci_shows_stale_and_official_warning(bot):
    from datetime import datetime, timedelta
    from pathlib import Path
    sent = []
    bot.send = lambda chat, text, markup=None, dry=True: sent.append(text)
    data_dir = Path(bot.cfg["_root"]) / "web" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    old = (datetime.now(UTC) - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data_dir.joinpath("outlook.json").write_text(json.dumps({
        "schema_version": 1,
        "generated": old,
        "coverage": {"expected": 1, "present": 1, "missing": []},
        "classes": {
            "small": {"label": "küçük", "limits": {}, "areas": [{
                "name": "Marmara Denizi",
                "windows": [{"start": "08:00", "end": "16:00", "level": "ok",
                             "gust_kn": 10, "wave_m": 0.4}],
                "return_by": None, "worst": "ok",
            }]},
            "medium": {"label": "m", "limits": {}, "areas": []},
            "large": {"label": "l", "limits": {}, "areas": []},
        },
    }, ensure_ascii=False), encoding="utf-8")
    data_dir.joinpath("warnings.json").write_text(json.dumps([{
        "headline": "Marmara için kuvvetli rüzgar uyarısı",
        "area": "Marmara",
        "org": "MGM",
        "kind": "marine-weather",
    }], ensure_ascii=False), encoding="utf-8")
    bot.handle(_msg(42, "/balikci marmara"))
    assert sent
    assert "Eski tahmin" in sent[0]
    assert "Resmi" in sent[0]
