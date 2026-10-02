"""Emergency webhook: one POST per new or changed incident, not one per cycle.

The same official notice is scraped every 15 minutes and merged into the stored
incident, so it is "touched" every cycle. These tests pin that it is announced
once, again only when its status/severity/type changes, and that the memory
survives a restart without ever breaking the cycle. No network: requests.post is
replaced."""

from __future__ import annotations

import json

import requests

import run
from src.model import Incident
from src.webhook_state import KEEP_SECONDS, WebhookState

URL = "http://127.0.0.1:8088/webhook/alert"


class _Resp:
    def __init__(self, code):
        self.status_code = code


def _fake_post(monkeypatch, codes=None):
    """Record every POST; answer with the next status code (200 when the list runs out)."""
    calls = []
    codes = list(codes or [])

    def post(url, json=None, headers=None, timeout=None):
        calls.append(json)
        code = codes.pop(0) if codes else 200
        if isinstance(code, Exception):
            raise code
        return _Resp(code)

    monkeypatch.setattr(requests, "post", post)
    return calls


def _inc(iid="rep-3d1b99ccb9", status="confirmed", severity="major", type_="capsize"):
    return Incident(id=iid, type=type_, status=status, severity=severity, area="Ege")


def _emit(state_path, *incs, url=URL):
    incidents = {i.id: i for i in incs}
    return run.emit_alerts(incidents, set(incidents), url, "test-token", state_path)


# --- dispatch_emergency_webhook -----------------------------------------------------


def test_dispatch_reports_success_only_for_2xx(monkeypatch):
    _fake_post(monkeypatch, [200, 500, requests.ConnectionError("down")])
    assert run.dispatch_emergency_webhook(URL, "t", {"event_id": "a"}) is True
    assert run.dispatch_emergency_webhook(URL, "t", {"event_id": "a"}) is False
    assert run.dispatch_emergency_webhook(URL, "t", {"event_id": "a"}) is False


def test_dispatch_without_or_with_unsafe_url_is_false_and_never_posts(monkeypatch):
    calls = _fake_post(monkeypatch)
    assert run.dispatch_emergency_webhook(None, "t", {}) is False
    assert run.dispatch_emergency_webhook("http://169.254.169.254/latest/", "t", {}) is False
    assert calls == []


# --- emit_alerts --------------------------------------------------------------------


def test_new_incident_is_emitted_and_remembered(tmp_path, monkeypatch):
    calls = _fake_post(monkeypatch)
    path = tmp_path / "data" / "webhook_state.json"
    assert _emit(path, _inc()) == 1
    assert [c["event_id"] for c in calls] == ["rep-3d1b99ccb9"]
    assert calls[0]["status"] == "confirmed" and calls[0]["priority"] == "major"
    row = json.loads(path.read_text("utf-8"))["sent"]["rep-3d1b99ccb9"]
    assert (row["status"], row["severity"], row["type"]) == ("confirmed", "major", "capsize")


def test_same_incident_next_cycle_is_not_resent(tmp_path, monkeypatch):
    # each emit_alerts call reloads the file, like a new cycle or a process restart
    calls = _fake_post(monkeypatch)
    path = tmp_path / "webhook_state.json"
    _emit(path, _inc())
    assert _emit(path, _inc()) == 0
    assert _emit(path, _inc()) == 0
    assert len(calls) == 1


def test_status_change_is_emitted_again(tmp_path, monkeypatch):
    # signal -> confirmed is what makes maritime-social post the Instagram story
    calls = _fake_post(monkeypatch)
    path = tmp_path / "webhook_state.json"
    _emit(path, _inc(status="signal"))
    assert _emit(path, _inc(status="confirmed")) == 1
    assert [c["status"] for c in calls] == ["signal", "confirmed"]
    assert _emit(path, _inc(status="confirmed")) == 0


def test_severity_or_type_change_is_emitted_again(tmp_path, monkeypatch):
    calls = _fake_post(monkeypatch)
    path = tmp_path / "webhook_state.json"
    _emit(path, _inc(severity="major"))
    assert _emit(path, _inc(severity="critical")) == 1
    assert _emit(path, _inc(severity="critical", type_="sinking")) == 1
    assert [(c["priority"], c["category"]) for c in calls] == [
        ("major", "capsize"),
        ("critical", "capsize"),
        ("critical", "sinking"),
    ]


def test_failed_post_is_not_recorded_and_retried_next_cycle(tmp_path, monkeypatch):
    calls = _fake_post(monkeypatch, [500, requests.ConnectionError("listener down"), 200])
    path = tmp_path / "webhook_state.json"
    assert _emit(path, _inc()) == 0
    assert not path.exists()
    assert _emit(path, _inc()) == 0
    assert _emit(path, _inc()) == 1
    assert _emit(path, _inc()) == 0
    assert len(calls) == 3


def test_minor_incident_is_never_sent(tmp_path, monkeypatch):
    calls = _fake_post(monkeypatch)
    path = tmp_path / "webhook_state.json"
    assert _emit(path, _inc(severity="minor")) == 0
    assert calls == []
    assert not path.exists()


def test_no_webhook_url_writes_no_state_file(tmp_path, monkeypatch):
    # GitHub Actions runs --once without a webhook: it must not create or touch the file
    calls = _fake_post(monkeypatch)
    path = tmp_path / "data" / "webhook_state.json"
    assert _emit(path, _inc(), url=None) == 0
    assert _emit(path, _inc(), url="") == 0
    assert calls == []
    assert not path.exists()
    assert not path.parent.exists()


def test_corrupt_state_file_is_treated_as_empty(tmp_path, monkeypatch):
    calls = _fake_post(monkeypatch)
    path = tmp_path / "webhook_state.json"
    for junk in ("{not json", "[1, 2, 3]", '{"sent": "x"}', ""):
        path.write_text(junk, encoding="utf-8")
        calls.clear()
        assert _emit(path, _inc()) == 1
        assert len(calls) == 1
        # and the next cycle reads the clean file it left behind
        assert _emit(path, _inc()) == 0


def test_corrupt_file_is_rewritten_even_when_nothing_is_sent(tmp_path, monkeypatch):
    _fake_post(monkeypatch)
    path = tmp_path / "webhook_state.json"
    path.write_text("\x00garbage", encoding="utf-8")
    _emit(path, _inc(severity="minor"))
    assert json.loads(path.read_text("utf-8"))["sent"] == {}


def test_bad_rows_are_dropped_good_rows_kept(tmp_path):
    path = tmp_path / "webhook_state.json"
    good = {"status": "confirmed", "severity": "major", "type": "capsize", "at": "2026-10-01T00:00:00Z"}
    path.write_text(json.dumps({"sent": {"a": good, "b": "oops", "c": None}}), encoding="utf-8")
    st = WebhookState(path)
    assert set(st.sent) == {"a"}
    assert not st.is_new_or_changed(_inc(iid="a"))


# --- pruning --------------------------------------------------------------------------


def test_prune_keeps_live_ids_and_recent_ones_drops_old_gone_ones(tmp_path):
    path = tmp_path / "webhook_state.json"
    st = WebhookState(path)
    now = 2_000_000_000.0
    old = now - KEEP_SECONDS - 3600
    st.record(_inc(iid="live-old"), now=old)  # still in the store: must not resend
    st.record(_inc(iid="gone-old"), now=old)  # left the store a week ago
    st.record(_inc(iid="gone-new"), now=now - 3600)  # may be scraped back under the same id
    st.sent["gone-bad-time"] = {"status": "confirmed", "severity": "major", "type": "x", "at": "?"}
    assert st.save({"live-old": object()}, now=now)
    kept = json.loads(path.read_text("utf-8"))["sent"]
    assert set(kept) == {"live-old", "gone-new"}


def test_save_without_changes_does_not_rewrite(tmp_path):
    path = tmp_path / "webhook_state.json"
    st = WebhookState(path)
    st.record(_inc())
    assert st.save({"rep-3d1b99ccb9": 1})
    assert WebhookState(path).save({"rep-3d1b99ccb9": 1}) is False
