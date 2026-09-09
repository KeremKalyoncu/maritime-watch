"""The daily outlook is the channel's main product, so it gets the most tests."""

import pytest

from src.process.window import DANGER, OK, build, level_for


def _times(n, start=6):
    return [f"2026-09-10T{(start + i) % 24:02d}:00" for i in range(n + 1)]


SMALL = {"gust_kn": 22, "wave_m": 1.25}


def test_small_craft_limits_are_not_a_cargo_ships():
    """Nine days of real Turkish coastal data crossed 34 kn four times and 2.0 m
    never. At the small-craft limit the same days had 371 unsafe point-hours."""
    assert level_for(25, 0.5, SMALL) == DANGER
    assert level_for(25, 0.5, {"gust_kn": 34, "wave_m": 2.0}) == OK   # nothing, to a ship
    assert level_for(10, 0.3, SMALL) == OK


def test_wave_alone_is_enough_to_stop_a_small_boat():
    assert level_for(12, 1.5, SMALL) == DANGER      # calm wind, big swell


def test_windows_say_when_not_just_how_much():
    gusts = [8] * 6 + [25] * 6
    waves = [0.2] * 12
    o = build("Marmara", _times(12), gusts, waves, SMALL, hours=12, tz_offset_h=0)
    assert [w.level for w in o.windows] == [OK, DANGER]
    assert o.windows[0].start == "06:00" and o.windows[0].end == "12:00"
    assert o.windows[1].start == "12:00"
    assert o.first_danger.start == "12:00"
    assert o.worst == DANGER


def test_a_one_hour_lull_between_two_blows_is_not_a_window():
    gusts = [25] * 4 + [8] + [25] * 4
    o = build("Ege", _times(9), gusts, [0.2] * 9, SMALL, hours=9, tz_offset_h=0)
    assert len(o.windows) == 1 and o.windows[0].level == DANGER


def test_local_time_is_used_not_utc():
    o = build("Marmara", _times(3, start=3), [8, 8, 8], [0.1] * 3, SMALL,
              hours=3, tz_offset_h=3)
    assert o.windows[0].start == "06:00"


def test_a_calm_day_produces_one_green_window():
    o = build("Antalya", _times(12), [9] * 12, [0.2] * 12, SMALL, hours=12, tz_offset_h=0)
    assert len(o.windows) == 1 and o.worst == OK and o.first_danger is None


def test_empty_forecast_is_not_a_calm_forecast(  ):
    o = build("Bos", [], [], [], SMALL)
    assert o.windows == [] and o.worst == OK and o.max_gust == 0


@pytest.mark.parametrize("field", ["times", "gusts"])
def test_a_dead_source_never_becomes_an_outlook(cfg, monkeypatch, field):
    """People plan a day around this message; a fixture-built one is worse than
    silence."""
    import requests

    from src.ingest import _net, openmeteo
    monkeypatch.setattr(_net, "SAMPLES_ALLOWED", False)
    monkeypatch.setattr(_net.requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(requests.RequestException("down")))
    assert openmeteo.fetch_forecast_points(cfg) == []


def test_outlook_message_names_the_hours_and_the_boat_class(cfg):
    from src.alert.telegram import Notifier
    cfg["secrets"] = {"telegram_token": "", "telegram_chat_id": "", "aisstream_key": ""}
    cfg["alert"]["telegram"]["digest"] = False
    klass = cfg["outlook"]["classes"]["small"]
    o = build("Marmara Denizi", _times(12), [8] * 6 + [26] * 6, [0.3] * 12,
              klass, hours=12, tz_offset_h=0)
    n = Notifier(cfg)
    sent = []
    n._send_one = lambda k, t, d, lat=None, lon=None: sent.append(t)
    n.daily_outlook([o], klass, dry=True, day="10.09.2026")
    assert sent
    msg = sent[0]
    assert "Marmara Denizi" in msg and "12:00" in msg
    assert "küçük tekne" in msg
    assert "ÇIKMAYIN" in msg
    assert "Model tahminidir" in msg          # never presented as measurement
    assert "158" in msg


def test_outlook_says_so_when_everywhere_is_under_the_limit(cfg):
    from src.alert.telegram import Notifier
    cfg["secrets"] = {"telegram_token": "", "telegram_chat_id": "", "aisstream_key": ""}
    cfg["alert"]["telegram"]["digest"] = False
    klass = cfg["outlook"]["classes"]["small"]
    o = build("Ege", _times(8), [7] * 8, [0.2] * 8, klass, hours=8, tz_offset_h=0)
    n = Notifier(cfg)
    sent = []
    n._send_one = lambda k, t, d, lat=None, lon=None: sent.append(t)
    n.daily_outlook([o], klass, dry=True, day="10.09.2026")
    assert "sınırın altında" in sent[0].lower()


def test_outlook_goes_out_once_a_day_even_though_cron_runs_every_15_minutes(cfg):
    from src.alert.telegram import Notifier
    cfg["secrets"] = {"telegram_token": "", "telegram_chat_id": "", "aisstream_key": ""}
    cfg["alert"]["telegram"]["digest"] = False
    klass = cfg["outlook"]["classes"]["small"]
    o = build("Marmara", _times(8), [26] * 8, [0.3] * 8, klass, hours=8, tz_offset_h=0)
    n = Notifier(cfg)
    sent = []

    def fake_send(key, text, dry, lat=None, lon=None):
        sent.append(key)
        n._remember(key)          # what the real sender does

    n._send_one = fake_send
    for _ in range(4):
        n.daily_outlook([o], klass, dry=True, day="10.09.2026")
    assert sent == ["outlook:10.09.2026"]
    n.daily_outlook([o], klass, dry=True, day="11.09.2026")
    assert len(sent) == 2          # next day speaks again


def _at_utc(monkeypatch, iso: str):
    """Freeze the clock at a UTC instant."""
    import calendar
    import time as _t

    import run
    epoch = calendar.timegm(_t.strptime(iso, "%Y-%m-%dT%H:%M"))
    monkeypatch.setattr(run.time, "time", lambda: epoch)


def test_the_hour_gate_runs_before_any_network_call(cfg, monkeypatch):
    """The cron fires every 15 minutes; the outlook must not fetch 96 times a day
    to find out it is not time yet."""
    import run
    cfg["outlook"]["send_hour_local"] = 6
    cfg["outlook"]["tz_offset_hours"] = 3
    calls = []
    monkeypatch.setattr(run, "fetch_forecast_points", lambda c: calls.append(1) or [])

    _at_utc(monkeypatch, "2026-09-10T01:00")        # 04:00 local - too early
    run.send_daily_outlook(cfg, None, dry=True)
    assert calls == []

    _at_utc(monkeypatch, "2026-09-10T04:00")        # 07:00 local - go
    run.send_daily_outlook(cfg, None, dry=True)
    assert calls == [1]


def test_outlook_off_by_config_sends_nothing(cfg, monkeypatch):
    import run
    cfg["outlook"]["enabled"] = False
    monkeypatch.setattr(run, "fetch_forecast_points",
                        lambda c: pytest.fail("must not fetch when disabled"))
    run.send_daily_outlook(cfg, None, dry=True)
