"""Per-chat subscriptions. A broadcast channel sends a Marmara fisherman twelve
sea areas they do not care about."""

import json

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


def test_a_subscriber_only_gets_the_areas_they_chose(cfg, monkeypatch, tmp_path):
    from src.alert.telegram import Notifier
    cfg["secrets"] = {"telegram_token": "", "telegram_chat_id": "", "aisstream_key": ""}
    times = [f"2026-09-10T{h:02d}:00" for h in range(13)]
    monkeypatch.setattr(
        "src.ingest.openmeteo.fetch_forecast_points",
        lambda c: [{"name": n, "lat": 41.0, "lon": 29.0, "times": times,
                    "gusts": [26] * 12, "waves": [0.3] * 12}
                   for n in ("Marmara Denizi", "Antalya Körfezi")])
    txt = Notifier(cfg).outlook_text_for(cfg, {"areas": ["Marmara Denizi"], "boat": "small"})
    assert "MARMARA DENİZİ" in txt          # Turkish uppercase, not "DENIZI"
    assert "Antalya" not in txt


def test_boat_class_changes_the_verdict_for_the_same_weather(cfg, monkeypatch):
    from src.alert.telegram import Notifier
    cfg["secrets"] = {"telegram_token": "", "telegram_chat_id": "", "aisstream_key": ""}
    times = [f"2026-09-10T{h:02d}:00" for h in range(13)]
    monkeypatch.setattr(
        "src.ingest.openmeteo.fetch_forecast_points",
        lambda c: [{"name": "Marmara Denizi", "lat": 41.0, "lon": 29.0, "times": times,
                    "gusts": [25] * 12, "waves": [0.4] * 12}])
    n = Notifier(cfg)
    assert "ÇIKMA" in n.outlook_text_for(cfg, {"areas": [], "boat": "small"})
    assert "ÇIKMA" not in n.outlook_text_for(cfg, {"areas": [], "boat": "large"})
