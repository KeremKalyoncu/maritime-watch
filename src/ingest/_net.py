"""Shared HTTP helpers. Every call falls back to a cached sample on failure."""

from __future__ import annotations

import json
from pathlib import Path

import requests

UA = {"User-Agent": "maritime-watch/1.0 (open-source maritime safety aggregator)"}
SAMPLES = Path(__file__).parent / "samples"
TIMEOUT = 10


def get_text(url: str, sample_name: str, headers: dict | None = None,
             timeout: int = TIMEOUT) -> tuple[str, bool]:
    try:
        r = requests.get(url, headers={**UA, **(headers or {})}, timeout=timeout)
        r.raise_for_status()
        # requests defaults to ISO-8859-1 when the header carries no charset,
        # which mangles Turkish RSS ("DAKÄ°KA"). Trust the byte sniff instead.
        ct = r.headers.get("content-type", "").lower()
        if "charset=" not in ct or (r.encoding or "").lower() in ("iso-8859-1", "latin-1"):
            r.encoding = r.apparent_encoding or r.encoding
        return r.text, True
    except Exception as e:
        print(f"[fetch] {url} down ({e}) -> sample {sample_name}")
        p = SAMPLES / sample_name
        return (p.read_text("utf-8") if p.exists() else ""), False


def get_json(url: str, sample_name: str, headers: dict | None = None,
             timeout: int = TIMEOUT):
    raw, live = get_text(url, sample_name, headers, timeout)
    if not raw:
        return None, live
    try:
        return json.loads(raw), live
    except json.JSONDecodeError:
        print(f"[fetch] {url}: response was not JSON")
        return None, live
