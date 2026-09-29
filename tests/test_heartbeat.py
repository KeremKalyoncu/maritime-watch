"""Dead-man switch ping: right URL, never printed, never crashes the loop."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("mw_run_hb", Path(__file__).resolve().parents[1] / "run.py")
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

URL = "https://hc-ping.com/00000000-test-uuid"


def test_ping_and_fail_urls(monkeypatch):
    import requests

    calls = []
    monkeypatch.setattr(requests, "get", lambda u, timeout: calls.append(u))
    assert run.heartbeat_ping(url=URL)
    assert run.heartbeat_ping(fail=True, url=URL + "/")
    assert calls == [URL, URL + "/fail"]


def test_no_url_is_noop(monkeypatch):
    monkeypatch.delenv("HEALTHCHECK_ENGINE_URL", raising=False)
    assert run.heartbeat_ping() is False


def test_network_error_is_swallowed_and_url_not_logged(monkeypatch, capsys):
    import requests

    def boom(u, timeout):
        raise requests.ConnectionError(f"cannot reach {u}")

    monkeypatch.setattr(requests, "get", boom)
    assert run.heartbeat_ping(url=URL) is False
    assert "hc-ping" not in capsys.readouterr().out
