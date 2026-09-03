"""Shared HTTP helpers. Every call falls back to a cached sample on failure."""

from __future__ import annotations

import json
from pathlib import Path

import requests

UA = {"User-Agent": "maritime-watch/1.0 (open-source maritime safety aggregator)"}
SAMPLES = Path(__file__).parent / "samples"
TIMEOUT = 15


def get_text(url: str, sample_name: str, headers: dict | None = None,
             timeout: int = TIMEOUT) -> tuple[str, bool]:
    try:
        r = requests.get(url, headers={**UA, **(headers or {})}, timeout=timeout)
        r.raise_for_status()
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
