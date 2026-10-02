"""data/health_history.jsonl: one short line per cycle, so "how often does a source
fail?" has an answer.

web/data/health.json only holds the last cycle and the phone's tmux log keeps 2000
lines that a restart wipes, so on 2026-10-02 nobody could say how often anything had
failed on the Note 4. Each line is ~200 bytes; KEEP lines is about three weeks of the
phone's 15 min loop (~400 KB). maritime-social reads it for the weekly admin report.

Fields (absent = nothing to report):
  t        cycle start, UTC ISO
  s        cycle seconds
  down     fetch endpoints that never answered this cycle (_net.STATUS keys)
  failed   ingest modules that raised (health "sources_down")
  om_miss  Open-Meteo areas with no forecast after the retry
  ais      AIS positions received in this cycle's capture (None: AIS off)
  vessels  vessels in the track store
  power    why the loop is slowing down (hot / low battery), else absent
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

KEEP = 2100


def forecast_missing(cfg: dict, points: list[dict] | None) -> list[str]:
    """Configured Open-Meteo areas the cycle got no forecast for."""
    got = {p.get("name") for p in points or []}
    return [p["name"] for p in (cfg.get("openmeteo") or {}).get("points") or [] if p["name"] not in got]


def entry(
    *,
    started: float,
    seconds: float,
    fetch_status: dict,
    sources_down: list[str],
    om_missing: list[str],
    ais_positions: int | None,
    vessels: int | None,
    power: str | None = None,
) -> dict:
    e: dict = {
        "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "s": round(seconds, 1),
        "ais": ais_positions,
        "vessels": vessels,
    }
    down = sorted(k for k, v in fetch_status.items() if v != "live")
    for key, val in (("down", down), ("failed", sorted(sources_down)), ("om_miss", om_missing), ("power", power)):
        if val:
            e[key] = val
    return e


def append(path: Path, e: dict, keep: int = KEEP) -> None:
    """Append one line; past keep + 10 % rewrite the newest `keep` lines atomically
    (a rewrite every ~200 cycles, not every cycle)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
    lines = path.read_text("utf-8").splitlines()
    if len(lines) > keep + keep // 10:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
        os.replace(tmp, path)
