"""JSON-file store. Current state lives in web/data/*.json, plus an append-only
events.jsonl log."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .model import Incident, Warning, now_iso
from .process.dedup import same_hazard

EVENT_LOG_MAX = 20000        # committed between CI runs, so keep it capped


class Store:
    def __init__(self, data_dir: str, log_dir: str | None = None):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = Path(log_dir) if log_dir else self.dir.parent.parent / "data"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.incidents_path = self.dir / "incidents.json"
        self.warnings_path = self.dir / "warnings.json"
        self.events_path = self.log_dir / "events.jsonl"

        self._lock = threading.Lock()
        self.incidents: dict[str, Incident] = {}
        self.warnings: dict[str, Warning] = {}
        self._load()

    def _load(self) -> None:
        if self.incidents_path.exists():
            for d in json.loads(self.incidents_path.read_text("utf-8") or "[]"):
                self.incidents[d["id"]] = Incident.from_dict(d)
        if self.warnings_path.exists():
            for d in json.loads(self.warnings_path.read_text("utf-8") or "[]"):
                self.warnings[d["id"]] = Warning.from_dict(d)

    def _event(self, kind: str, payload: dict) -> None:
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": now_iso(), "kind": kind, "payload": payload}, ensure_ascii=False) + "\n")

    def trim_events(self, max_lines: int = EVENT_LOG_MAX) -> int:
        """The event log is committed between CI runs, so cap it. Stats read the
        whole file but only the recent tail matters."""
        if not self.events_path.exists():
            return 0
        lines = self.events_path.read_text("utf-8").splitlines()
        if len(lines) <= max_lines:
            return 0
        joined = "\n".join(lines[-max_lines:]) + "\n"
        self.events_path.write_text(joined, encoding="utf-8")
        return len(lines) - max_lines

    def upsert_incident(self, inc: Incident) -> Incident:
        with self._lock:
            cur = self.incidents.get(inc.id)
            if cur is None:
                self.incidents[inc.id] = inc
                self._event("incident_new", inc.to_dict())
                return inc

            changed = False
            for s in inc.sources:
                changed |= cur.add_source(s)
            if inc.lat and not cur.lat:
                cur.lat, changed = inc.lat, True
            if inc.lon and not cur.lon:
                cur.lon, changed = inc.lon, True
            if inc.casualties is not None and inc.casualties != cur.casualties:
                cur.casualties, changed = inc.casualties, True
            if inc.type != "unknown" and cur.type == "unknown":
                cur.type, changed = inc.type, True
            if inc.vessel.mmsi and not cur.vessel.mmsi:
                cur.vessel, changed = inc.vessel, True
            if changed:
                cur.last_update = now_iso()
                self._event("incident_update", cur.to_dict())
            return cur

    def upsert_warning(self, w: Warning) -> tuple[Warning, str]:
        """Returns (warning, how) where how is 'new', 'merged' or 'dup'."""
        with self._lock:
            def _refresh(cur: Warning) -> None:
                # same source re-reported: update the live figures, don't add a
                # "source" and don't count it as an independent confirmation
                cur.headline = w.headline
                cur.value = w.value
                cur.severity = w.severity
                cur.lat, cur.lon = w.lat, w.lon
                cur.issued = w.issued
                cur.last_update = now_iso()

            if w.id in self.warnings:
                _refresh(self.warnings[w.id])
                return self.warnings[w.id], "refreshed"

            new_orgs = {s.org for s in w.sources if s.org}
            for cur in self.warnings.values():
                if not same_hazard(cur, w):
                    continue
                if new_orgs and new_orgs.issubset(set(cur.orgs)):
                    _refresh(cur)
                    return cur, "refreshed"
                added = False
                for s in w.sources:
                    added |= cur.add_source(s)
                if w.severity == "major" and cur.severity != "major":
                    cur.severity = "major"
                if w.value is not None and cur.value is None:
                    cur.value = w.value
                if added:
                    cur.last_update = now_iso()
                    self._event("warning_merge", cur.to_dict())
                    return cur, "merged"
                return cur, "dup"

            self.warnings[w.id] = w
            self._event("warning_new", w.to_dict())
            return w, "new"

    def active_incidents(self) -> list[Incident]:
        return list(self.incidents.values())

    def active_warnings(self) -> list[Warning]:
        return list(self.warnings.values())

    def save(self) -> None:
        with self._lock:
            self.incidents_path.write_text(
                json.dumps([i.to_dict() for i in self.incidents.values()], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.warnings_path.write_text(
                json.dumps([w.to_dict() for w in self.warnings.values()], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
