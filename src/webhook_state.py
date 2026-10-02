"""Which incidents the emergency webhook already announced, and in what state.

cycle() webhooks the major/critical incidents it touched, and "touched" also holds
the ones merely seen again: an official Sahil Güvenlik notice is scraped every
15 minutes and merged into the stored incident each time. Without a memory the
same two incidents were POSTed to maritime-social every cycle for a whole day; its
own cache dropped them, but that left the receiver as the only safety net.

An incident goes out again only when something the receiver acts on changes: its
status (signal -> confirmed is what posts the Instagram story), severity or type.

The file sits in data/ next to the other engine state, so a restart or a
note4_sync (which carries data/ across the git reset) does not resend everything.
Only the phone runs with a webhook, so the file is gitignored and CI never makes it.
"""

from __future__ import annotations

import calendar
import json
import os
import time
from pathlib import Path

ISO = "%Y-%m-%dT%H:%M:%SZ"
FIELDS = ("status", "severity", "type")
# Ids that left the store are remembered this long: the store can drop an incident
# while the source page still lists the notice, and the next scrape recreates it under
# the same id. That is not news for the channel. Ids still in the store never expire.
KEEP_SECONDS = 7 * 24 * 3600


def _plain(v) -> str:
    # str+Enum members and plain strings both turn up; compare the raw value
    return str(getattr(v, "value", v) or "")


def fingerprint(inc) -> dict:
    return {f: _plain(getattr(inc, f, "")) for f in FIELDS}


def _epoch(stamp) -> float | None:
    try:
        return float(calendar.timegm(time.strptime(str(stamp), ISO)))
    except (TypeError, ValueError, OverflowError):
        return None


class WebhookState:
    """{incident id: {status, severity, type, at}} as of the last successful POST."""

    def __init__(self, path):
        self.path = Path(path)
        self._dirty = False
        self.sent = self._load()

    def _load(self) -> dict:
        try:
            if not self.path.exists():
                return {}
            data = json.loads(self.path.read_text("utf-8") or "{}")
            rows = data.get("sent") if isinstance(data, dict) else None
            if not isinstance(rows, dict):
                raise ValueError("no 'sent' map")
        except Exception as e:
            # A half-written or hand-edited file must never stop the cycle. Starting
            # empty resends what is still active once; the receiver's cache drops repeats.
            print(f"[webhook:state] unreadable, starting empty: {e}")
            self._dirty = True  # write a clean file back instead of warning every cycle
            return {}
        good = {str(k): v for k, v in rows.items() if isinstance(v, dict)}
        if len(good) != len(rows):
            self._dirty = True
        return good

    def is_new_or_changed(self, inc) -> bool:
        last = self.sent.get(inc.id)
        if last is None:
            return True
        return any(_plain(last.get(f)) != v for f, v in fingerprint(inc).items())

    def record(self, inc, now: float | None = None) -> None:
        row = fingerprint(inc)
        row["at"] = time.strftime(ISO, time.gmtime(now))
        self.sent[inc.id] = row
        self._dirty = True

    def prune(self, live_ids, now: float | None = None) -> int:
        now = time.time() if now is None else now
        gone = []
        for iid, row in self.sent.items():
            if iid in live_ids:
                continue
            at = _epoch(row.get("at"))
            if at is None or now - at > KEEP_SECONDS:
                gone.append(iid)
        for iid in gone:
            del self.sent[iid]
        if gone:
            self._dirty = True
        return len(gone)

    def save(self, live_ids, now: float | None = None) -> bool:
        """Prune, then write only if something changed. Never raises."""
        self.prune(live_ids, now)
        if not self._dirty:
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps({"version": 1, "sent": dict(sorted(self.sent.items()))}, ensure_ascii=False, indent=1)
            # temp + replace: a phone that dies mid-write leaves the old file, not half a new one
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(raw, encoding="utf-8")
            os.replace(str(tmp), str(self.path))
        except Exception as e:
            print(f"[webhook:state] write failed: {e}")
            return False
        self._dirty = False
        return True
