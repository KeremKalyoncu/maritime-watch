"""Rule-based AIS anomaly checks.

  nav-status   NavigationalStatus 2 (not under command) or 6 (aground)
  speed-drop   was under way, now stopped for 2+ samples, and not anchored
  course-spike near-reversal by a cargo/tanker under way (off by default: an
               ordinary 60-degree turn produced 44 false flags in one live cycle)
  ais-gap      an under-way vessel missing for several CONSECUTIVE cycles, not
               merely absent from one 90-second burst, and not explainable by
               having reached port or left the subscribed box

Tracks are kept in data/vessels.json between cycles so the gap and track rules
work across the short captures.
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


def _iso(ts) -> str:
    """aisstream sends '2026-09-04 21:36:32.547386925 +0000 UTC'. Storing that
    verbatim triples the size of every track point and defeats git deltas."""
    if not ts:
        return ""
    e = _parse_ts(str(ts))
    if e is None:
        return str(ts)[:19]
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(e))


def _round(x, nd=4):
    # AIS resolution is ~0.0001 deg (11 m); 16 significant digits is noise
    return round(x, nd) if isinstance(x, (int, float)) else x
def _near_bbox_edge(lat, lon, bbox, margin_deg: float = 0.35) -> bool:
    """A vessel that simply sailed out of the subscribed box is not 'missing'."""
    if not bbox or lat is None or lon is None:
        return False
    return (lat - bbox["lat_min"] < margin_deg or bbox["lat_max"] - lat < margin_deg
            or lon - bbox["lon_min"] < margin_deg or bbox["lon_max"] - lon < margin_deg)


def _near_port(lat, lon, nm: float = 6.0) -> bool:
    """Arriving and switching the transponder off is routine, not a disappearance."""
    from .classify import nearest_port
    np = nearest_port(lat, lon)
    return np is not None and np[1] <= nm
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
                "lat": _round(p["lat"]), "lon": _round(p["lon"]),
                "sog": _round(p.get("sog"), 1), "cog": _round(p.get("cog"), 1),
                "nav": p.get("nav_status"), "ts": _iso(p.get("ts")),
            })
            v["track"] = v["track"][-self.history:]
            v["last_seen"] = _iso(p.get("ts"))

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
        # sorted + one line per vessel: this file is committed every cycle, and a
        # single unsorted line makes git rewrite all 170 KB each time
        rows = [json.dumps(k) + ":" + json.dumps(v, ensure_ascii=False, sort_keys=True)
                for k, v in sorted(self.data.items())]
        self.path.write_text("{" + ",\n".join(rows) + "}", encoding="utf-8")


def _gap_anomalies(cand, tracked: int, a: dict) -> list[Anomaly]:
    """Drop cohorts that went quiet together.

    A vessel in trouble stops transmitting on its own. When a dozen ships share
    the same silence to the minute it is our receiver that stopped - a dropped
    aisstream socket, or a cron run that never fired - and one live cycle turned
    that into 31 "missing vessel" alerts. Same start minute, same cause, no news.
    """
    max_cluster = a.get("gap_max_cluster", 3)
    buckets: dict[int, int] = {}
    for _mmsi, _v, gap_min, _lat, _lon in cand:
        buckets[int(gap_min // 10)] = buckets.get(int(gap_min // 10), 0) + 1

    share = a.get("gap_max_share", 0.25)
    if tracked and len(cand) > max(max_cluster, tracked * share):
        print(f"[anomaly] {len(cand)}/{tracked} takip edilen gemi ayni anda sustu "
              f"-> AIS beslemesi kesintisi, ais-gap uyarilari atlandi")
        return []

    out = []
    for mmsi, v, gap_min, lat, lon in cand:
        if buckets[int(gap_min // 10)] > max_cluster:
            continue
        out.append(Anomaly(mmsi, "ais-gap",
                           f"seyir halindeyken AIS sinyali yaklaşık {gap_min:.0f} dakika önce "
                           f"kesildi ({v['misses']} taramada üst üste görünmedi)",
                           lat, lon, "major", v.get("name", "")))
    return out


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

        # A 60-degree turn is ordinary navigation (traffic separation schemes,
        # Bosphorus bends, port approaches) - in one live cycle this rule alone
        # produced 44 of 83 flags, essentially all false. It now needs a
        # near-reversal AND a ship type that has no business making one.
        if a.get("course_spike_enabled", False):
            cogs = [t["cog"] for t in track if t.get("cog") is not None][-3:]
            if (len(cogs) >= 2 and prof["sensitive"]
                    and any((s or 0) > a["moving_speed_kn"] for s in sogs[-3:])):
                d = max(min(abs(cogs[i] - cogs[i - 1]) % 360, 360 - abs(cogs[i] - cogs[i - 1]) % 360)
                        for i in range(1, len(cogs)))
                if d >= a.get("course_reversal_deg", 120):
                    out.append(Anomaly(int(key), "course-spike", f"ani rota değişimi (~{d:.0f}°)",
                                       p["lat"], p["lon"], "minor", name))

    # ais-gap: we sample ~90 s out of every cron interval, so a vessel simply not
    # transmitting during this burst is NOT missing. Absence only means something
    # after several consecutive cycles, and not when the vessel plausibly just
    # arrived (near a port) or sailed out of the subscribed box.
    now = time.time()
    bbox = cfg.get("region", {}).get("bbox")
    min_misses = a.get("gap_min_cycles", 3)
    cand: list[tuple[int, dict, float, float, float]] = []
    # the whole fleet we hold a usable track for, heard this cycle or not - the
    # denominator for "is it them or is it us"
    tracked = sum(1 for v in state.data.values() if len(v.get("track", [])) >= 3)
    for key, v in state.data.items():
        if key in seen_now:
            v["misses"] = 0
            continue
        v["misses"] = v.get("misses", 0) + 1
        track = v.get("track", [])
        if len(track) < 3:
            continue
        if v["misses"] < min_misses:
            continue
        last_ts = _parse_ts(v.get("last_seen"))
        if last_ts is None:
            continue
        gap_min = (now - last_ts) / 60.0
        if gap_min < a["gap_minutes"] or gap_min > a.get("gap_max_minutes", 24 * 60):
            continue
        if (track[-1].get("sog") or 0) < a["moving_speed_kn"]:
            continue
        lat, lon = track[-1]["lat"], track[-1]["lon"]
        if _near_bbox_edge(lat, lon, bbox) or _near_port(lat, lon):
            continue
        cand.append((int(key), v, gap_min, lat, lon))

    out.extend(_gap_anomalies(cand, tracked, a))
    return out
