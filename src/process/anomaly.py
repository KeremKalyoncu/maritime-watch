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

from .shiptype import CATEGORY_TR as SHIP_CAT_TR
from .shiptype import category as ship_category
from .shiptype import profile as ship_profile

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
            if p.get("msg_type") == "safety":
                continue
            if p.get("mmsi") is None or p.get("lat") is None or p.get("lon") is None:
                continue
            key = str(p["mmsi"])
            v = self.data.setdefault(key, {"track": [], "name": ""})
            if p.get("name"):
                v["name"] = p["name"]
            if p.get("type_code") is not None:
                v["type_code"] = p["type_code"]
            v["track"].append({
                "lat": p["lat"], "lon": p["lon"], "sog": p.get("sog"),
                "cog": p.get("cog"), "nav": p.get("nav_status"), "ts": p.get("ts"),
            })
            v["track"] = v["track"][-self.history:]
            v["last_seen"] = p.get("ts")

    def prune(self, ttl_hours: float = 12.0, max_vessels: int = 4000) -> int:
        """Forget vessels not heard from in a while, so the persisted state stays
        small enough to live in the repo between CI runs."""
        now = time.time()
        before = len(self.data)
        for key, v in list(self.data.items()):
            ts = _parse_ts(v.get("last_seen"))
            if ts is not None and (now - ts) / 3600.0 > ttl_hours:
                del self.data[key]
        if len(self.data) > max_vessels:
            ranked = sorted(self.data.items(),
                            key=lambda kv: _parse_ts(kv[1].get("last_seen")) or 0, reverse=True)
            self.data = dict(ranked[:max_vessels])
        return before - len(self.data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


def detect(state: VesselState, positions: list[dict], cfg: dict, seen_now: set[str]) -> list[Anomaly]:
    a = cfg["anomaly"]
    prefixes = tuple(cfg.get("ais", {}).get("distress_mmsi_prefixes", ("970", "972", "974")))
    out: list[Anomaly] = []

    latest: dict[str, dict] = {}
    for p in positions:
        if p.get("msg_type") == "safety":
            continue
        if p.get("mmsi") is not None:
            latest[str(p["mmsi"])] = p

    # AIS distress transmitters (SART / MOB / EPIRB-AIS): the MMSI itself is the alert
    for key, p in latest.items():
        if key.startswith(prefixes) and p.get("lat") is not None:
            kind = {"970": "AIS-SART", "972": "MOB (denize adam düştü)",
                    "974": "EPIRB-AIS"}.get(key[:3], "AIS tehlike vericisi")
            out.append(Anomaly(int(key), "ais-sart", f"{kind} sinyali alındı",
                               p["lat"], p["lon"], "critical",
                               p.get("name") or state.data.get(key, {}).get("name", "")))

    # rules driven by the current position plus the stored track
    for key, p in latest.items():
        nav = p.get("nav_status")
        vstate = state.data.get(key, {})
        name = p.get("name") or vstate.get("name", "")
        track = vstate.get("track", [])
        prof = ship_profile(p.get("type_code", vstate.get("type_code")))
        cat = ship_category(p.get("type_code", vstate.get("type_code")))

        if nav in NAV_STATUS:
            out.append(Anomaly(int(key), "nav-status", NAV_STATUS[nav], p["lat"], p["lon"],
                               "critical" if nav == 6 else "major", name))

        sogs = [t["sog"] for t in track if t.get("sog") is not None]
        if prof["speed_drop"] and len(sogs) >= 3:
            move_bar = a["moving_speed_kn"] * (0.6 if prof["sensitive"] else 1.0)
            was_moving = max(sogs[:-1]) >= move_bar
            sustained_stop = sogs[-1] <= a["stopped_speed_kn"] and sogs[-2] <= a["stopped_speed_kn"]
            if was_moving and sustained_stop and nav not in (1, 5):  # not anchored / moored
                label = SHIP_CAT_TR.get(cat, "")
                sev = "major" if not prof["sensitive"] else "critical"
                detail = f"{label + ' ' if label and label != 'bilinmiyor' else ''}".strip()
                detail = (f"{detail}: " if detail else "") + \
                         f"seyir hızından ({max(sogs[:-1]):.1f} kn) ani duruşa geçti"
                out.append(Anomaly(int(key), "speed-drop", detail, p["lat"], p["lon"], sev, name))

        cogs = [t["cog"] for t in track if t.get("cog") is not None][-3:]
        if len(cogs) >= 2 and any((s or 0) > a["moving_speed_kn"] for s in sogs[-3:]):
            d = max(min(abs(cogs[i] - cogs[i - 1]) % 360, 360 - abs(cogs[i] - cogs[i - 1]) % 360)
                    for i in range(1, len(cogs)))
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
