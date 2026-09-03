#!/usr/bin/env python3
"""Experimental reference. Not imported by the app. See README.md in this folder.

WAV in -> whisper-cli (if present) -> keyword match -> one metadata line in
data/sdr_hits.jsonl. No transcript text is written anywhere. Receive-only,
permitted frequencies only, no archiving. Read the legal design rules first.

Usage:
    py src/sdr/sentinel_stub.py path/to/clip.wav 156.800
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

KEYWORDS = [
    r"mayday", r"pan[ -]?pan", r"imdat", r"batıyor", r"su alıyor", r"alabora",
    r"denize düş", r"yaralı", r"kurtar", r"yardım", r"mahsur",
]
HITS = Path(__file__).resolve().parents[2] / "data" / "sdr_hits.jsonl"
WHISPER_BIN = "whisper-cli"          # or an absolute path to whisper.cpp build
WHISPER_MODEL = "models/ggml-small.bin"


def transcribe(wav: str) -> str:
    if not shutil.which(WHISPER_BIN):
        print(f"[sdr] {WHISPER_BIN} not found on PATH, nothing to do")
        return ""
    try:
        r = subprocess.run(
            [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", wav, "-l", "tr", "-nt", "--no-timestamps"],
            capture_output=True, text=True, timeout=120, check=True,
        )
        return r.stdout.strip()
    except Exception as e:
        print(f"[sdr] whisper error: {e}")
        return ""


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    wav, freq = sys.argv[1], sys.argv[2]
    text = transcribe(wav)
    if not text:
        return
    kw = next((k for k in KEYWORDS if re.search(k, text, re.IGNORECASE)), None)
    if not kw:
        print("[sdr] no keyword, discarding (no transcript stored)")
        return
    HITS.parent.mkdir(parents=True, exist_ok=True)
    with HITS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "freq": freq,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "keyword": re.sub(r"[^a-zçğıöşü ]", "", kw),
            "confidence": 0.15,
        }, ensure_ascii=False) + "\n")
    print(f"[sdr] hit on /{kw}/ at {freq}: metadata written, transcript discarded")


if __name__ == "__main__":
    main()
