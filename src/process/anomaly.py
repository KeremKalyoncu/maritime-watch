"""Rule-based AIS anomaly checks.

  nav-status   NavigationalStatus 2 (not under command) or 6 (aground)
  speed-drop   was under way, now stopped for 2+ samples, and not anchored
  course-spike large course change while under way
  ais-gap      an under-way vessel goes silent for gap_minutes or more

Tracks are kept in data/vessels.json between cycles so the gap and track rules
still work across the short captures.
"""

from __future__ import annotations

import calendar
import json
import time
from dataclasses import dataclass
from pathlib import Path

NAV_STATUS = {
    2: "kumanda dışı (not under command)",
    6: "karaya oturmuş (aground)",
}


@dataclass
class Anomaly:
    mmsi: int
    kind: str
    detail: str
    lat: float
    lon: float
    severity: str          # minor | major | critical
    name: str = ""


def _parse_ts(s: str | None):
    # ISO-ish UTC string -> epoch seconds
    if not s:
        return None
    s = s.replace("Z", "").split(".")[0].split(" +")[0].replace(" UTC", "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return calendar.timegm(time.strptime(s, fmt))
        except ValueError:
            continue
    return None


class VesselState:
    """Per-MMSI rolling track, persisted as JSON."""

    def __init__(self, path: str, history: int):
        self.path = Path(path)
        self.history = history
        self.data: dict[str, dict] = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text("utf-8") or "{}")
            except json.JSONDecodeError:
                self.data = {}

    def update(self, positions: list[dict]) -> None:
        for p in positions:
            if p.get("mmsi") is None or p.get("lat") is None or p.get("lon") is None:
                continue
            key = str(p["mmsi"])
            v = self.data.setdefault(key, {"track": [], "name": ""})
            if p.get("name"):
                v["name"] = p["name"]
            v["track"].append({
                "lat": p["lat"], "lon": p["lon"], "sog": p.get("sog"),
                "cog": p.get("cog"), "nav": p.get("nav_status"), "ts": p.get("ts"),
            })
            v["track"] = v["track"][-self.history:]
            v["last_seen"] = p.get("ts")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


def detect(state: VesselState, positions: list[dict], cfg: dict, seen_now: set[str]) -> list[Anomaly]:
    a = cfg["anomaly"]
    out: list[Anomaly] = []

    latest: dict[str, dict] = {}
    for p in positions:
        if p.get("mmsi") is not None:
            latest[str(p["mmsi"])] = p

    # rules driven by the current position plus the stored track
    for key, p in latest.items():
        nav = p.get("nav_status")
        name = p.get("name") or state.data.get(key, {}).get("name", "")
        track = state.data.get(key, {}).get("track", [])

        if nav in NAV_STATUS:
            out.append(Anomaly(int(key), "nav-status", NAV_STATUS[nav], p["lat"], p["lon"],
                               "critical" if nav == 6 else "major", name))

        sogs = [t["sog"] for t in track if t.get("sog") is not None]
        if len(sogs) >= 3:
            was_moving = max(sogs[:-1]) >= a["moving_speed_kn"]
            sustained_stop = sogs[-1] <= a["stopped_speed_kn"] and sogs[-2] <= a["stopped_speed_kn"]
            if was_moving and sustained_stop and nav not in (1, 5):  # not anchored / moored
                out.append(Anomaly(int(key), "speed-drop",
                                   f"seyir hızından ({max(sogs[:-1]):.1f} kn) ani duruşa geçti",
                                   p["lat"], p["lon"], "major", name))

        cogs = [t["cog"] for t in track if t.get("cog") is not None]
        if len(cogs) >= 2 and any((s or 0) > a["moving_speed_kn"] for s in sogs[-3:]):
            d = abs(cogs[-1] - cogs[-2]) % 360
            d = min(d, 360 - d)
            if d >= a["course_change_deg"]:
                out.append(Anomaly(int(key), "course-spike", f"ani rota değişimi (~{d:.0f}°)",
                                   p["lat"], p["lon"], "minor", name))

    # ais-gap: a vessel we were tracking under way is missing this cycle
    now = time.time()
    for key, v in state.data.items():
        if key in seen_now:
            continue
        track = v.get("track", [])
        if len(track) < 3:
            continue
        last_ts = _parse_ts(v.get("last_seen"))
        if last_ts is None:
            continue
        gap_min = (now - last_ts) / 60.0
        if a["gap_minutes"] <= gap_min <= a["gap_minutes"] * 8 and (track[-1].get("sog") or 0) >= a["moving_speed_kn"]:
            out.append(Anomaly(int(key), "ais-gap",
                               f"seyir halindeyken AIS sinyali ~{gap_min:.0f} dk önce kesildi",
                               track[-1]["lat"], track[-1]["lon"], "major", v.get("name", "")))
    return out
