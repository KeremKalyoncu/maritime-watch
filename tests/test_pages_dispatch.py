"""The phone asks GitHub to rebuild the public map (K26): src/pages_dispatch.py, offline."""

import inspect

import run
from src import health_history as hh
from src.pages_dispatch import REFUSED_BACKOFF_S, PagesDispatch

TOKEN = "github_pat_FAKEfakeFAKEfakeFAKEfakeFAKEfake0123456789"
CFG = {"publish": {"dispatch": {"repo": "KeremKalyoncu/maritime-watch", "workflow": "update.yml",
                                "ref": "main", "every_minutes": 30}}}


class Resp:
    def __init__(self, code):
        self.status_code = code


class Session:
    def __init__(self, *codes, boom=False):
        self.codes, self.boom, self.calls = list(codes), boom, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if self.boom:
            raise ConnectionError(f"failed with Authorization: Bearer {TOKEN}")
        return Resp(self.codes.pop(0))


def _pd(*codes, boom=False, token=TOKEN, cfg=CFG):
    now = [1_000_000.0]
    s = Session(*codes, boom=boom)
    return PagesDispatch(cfg, token=token, session=s, clock=lambda: now[0]), s, now


def test_no_token_means_no_request():
    pd, s, _ = _pd(token="")
    assert pd.maybe_dispatch() is None and s.calls == []


def test_dispatch_hits_the_workflow_endpoint_with_actions_scope_only():
    pd, s, _ = _pd(204)
    assert pd.maybe_dispatch() == "ok"
    call = s.calls[0]
    assert call["url"] == "https://api.github.com/repos/KeremKalyoncu/maritime-watch/actions/workflows/update.yml/dispatches"
    assert call["json"] == {"ref": "main"}
    assert call["headers"]["Authorization"] == f"Bearer {TOKEN}" and call["timeout"] == 10


def test_at_most_once_per_interval():
    pd, s, now = _pd(204, 200)
    assert pd.maybe_dispatch() == "ok"
    now[0] += 29 * 60
    assert pd.maybe_dispatch() is None  # the 15 min loop asks every other cycle
    now[0] += 60
    assert pd.maybe_dispatch() == "ok"  # 200 (newer API answer) is fine too
    assert len(s.calls) == 2


def test_a_refused_token_backs_off_six_hours(capsys):
    pd, s, now = _pd(401, 204)
    assert pd.maybe_dispatch() == "refused"
    now[0] += REFUSED_BACKOFF_S - 1
    assert pd.maybe_dispatch() is None
    now[0] += 1
    assert pd.maybe_dispatch() == "ok"
    assert TOKEN not in capsys.readouterr().out


def test_server_errors_and_network_errors_retry_next_cycle(capsys):
    pd, s, now = _pd(502, 204)
    assert pd.maybe_dispatch() == "http_502"
    assert pd.maybe_dispatch() == "ok"  # no success yet, so the next cycle is due
    pd2, _, _ = _pd(boom=True)
    assert pd2.maybe_dispatch() == "error"
    out = capsys.readouterr().out
    assert TOKEN not in out and "Bearer" not in out  # exception text is never printed


def test_disabled_in_config():
    pd, s, _ = _pd(204, cfg={"publish": {"dispatch": {"enabled": False}}})
    assert pd.maybe_dispatch() is None and s.calls == []


def test_only_the_loop_dispatches():
    # --once (GitHub's own run) calls cycle() without pages: a run never triggers the next one
    assert inspect.signature(run.cycle).parameters["pages"].default is None


def test_history_records_the_outcome():
    e = hh.entry(started=0, seconds=1, fetch_status={}, sources_down=[], om_missing=[],
                 ais_positions=None, vessels=None, pages="refused")
    assert e["pages"] == "refused"
    assert "pages" not in hh.entry(started=0, seconds=1, fetch_status={}, sources_down=[], om_missing=[],
                                   ais_positions=None, vessels=None)
