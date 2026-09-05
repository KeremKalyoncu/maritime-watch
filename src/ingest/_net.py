"""Shared HTTP helpers.

SAFETY RULE: the cached copies in ./samples exist so the tests and a fresh clone
can run offline. They are fixtures, not data. If they reach the published output
the project fabricates a warning — which already happened once: a dead Open-Meteo
fetch put the fixture's "dalga 2.7 m, ruzgar 41 kn" on the live Telegram channel
as a real forecast for two different sea areas.

So sample fallback is a switch, and production turns it OFF. `run.py` sets
`SAMPLES_ALLOWED` from `sources.use_samples_when_down` (default false); with it
off a dead source returns empty and every ingest module yields nothing, which is
the correct behaviour — say nothing rather than say something false.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

UA = {"User-Agent": "maritime-watch/1.0 (open-source maritime safety aggregator)"}
SAMPLES = Path(__file__).parent / "samples"
TIMEOUT = 10

# True in tests and offline demos, False in production (set by run.py from config)
SAMPLES_ALLOWED = True

# per-cycle record of how each source answered: "live" | "sample" | "down"
STATUS: dict[str, str] = {}


def reset_status() -> None:
    STATUS.clear()


def get_text(url: str, sample_name: str, headers: dict | None = None,
             timeout: int = TIMEOUT) -> tuple[str, bool]:
    """Returns (text, is_live). Never returns sample text when SAMPLES_ALLOWED is off."""
    try:
        r = requests.get(url, headers={**UA, **(headers or {})}, timeout=timeout)
        r.raise_for_status()
        # requests defaults to ISO-8859-1 when the header carries no charset,
        # which mangles Turkish RSS ("DAKÄ°KA"). Trust the byte sniff instead.
        ct = r.headers.get("content-type", "").lower()
        if "charset=" not in ct or (r.encoding or "").lower() in ("iso-8859-1", "latin-1"):
            r.encoding = r.apparent_encoding or r.encoding
        STATUS[sample_name] = "live"
        return r.text, True
    except Exception as e:
        p = SAMPLES / sample_name
        if SAMPLES_ALLOWED and p.exists():
            print(f"[fetch] {url} down ({e}) -> sample {sample_name} (NOT publishable)")
            STATUS[sample_name] = "sample"
            return p.read_text("utf-8"), False
        print(f"[fetch] {url} down ({e}) -> yayin yok")
        STATUS[sample_name] = "down"
        return "", False


def get_json(url: str, sample_name: str, headers: dict | None = None,
             timeout: int = TIMEOUT):
    raw, live = get_text(url, sample_name, headers, timeout)
    if not raw:
        return None, live
    try:
        return json.loads(raw), live
    except json.JSONDecodeError:
        print(f"[fetch] {url}: response was not JSON")
        STATUS[sample_name] = "down"
        return None, live
