#!/usr/bin/env python3
"""Measure the pipeline against eval/labels.json and write eval/REPORT.md.

    py eval/run_eval.py

Covers: the news keyword filter, the text extractor, and the AIS anomaly rules.
Synthetic tracks; headlines paraphrased from real Turkish coverage.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.ingest.news import _match, _norm  # noqa: E402
from src.process.anomaly import VesselState, detect  # noqa: E402
from src.process.extract import extract  # noqa: E402

_CFG = load_config()

LABELS = json.loads((Path(__file__).parent / "labels.json").read_text("utf-8"))
CFG_ANOM = {
    "anomaly": {"moving_speed_kn": 3.0, "stopped_speed_kn": 0.5, "gap_minutes": 45,
                "course_change_deg": 60},
    "ais": {"distress_mmsi_prefixes": ["970", "972", "974"]},
}


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


# --------------------------------------------------------------- news filter
def eval_news():
    import re
    mari = [_norm(w) for w in _CFG["news"]["maritime_words"]]
    inci = [_norm(w) for w in _CFG["news"]["incident_words"]]
    tp = fp = fn = tn = 0
    misses = []
    for c in LABELS["news"]:
        low = _norm(c["text"])
        toks = re.findall(r"[a-zçğıöşü]+", low)
        pred = _match(low, toks, mari) and _match(low, toks, inci)
        if pred and c["label"]:
            tp += 1
        elif pred and not c["label"]:
            fp += 1
            misses.append(f"FP: {c['text']}")
        elif not pred and c["label"]:
            fn += 1
            misses.append(f"FN: {c['text']}")
        else:
            tn += 1
    return ("News keyword filter", _prf(tp, fp, fn), (tp, fp, fn, tn), misses)


# ---------------------------------------------------------------- extractor
def eval_extract():
    ok = total = 0
    misses = []
    for c in LABELS["extract"]:
        e = extract(c["text"])
        checks = []
        if "vessel" in c:
            checks.append((e.vessel == c["vessel"], f"vessel={e.vessel!r} exp={c['vessel']!r}"))
        if "casualties" in c:
            checks.append((e.casualties == c["casualties"], f"cas={e.casualties} exp={c['casualties']}"))
        if c.get("coords"):
            checks.append((e.lat is not None, f"coords={e.lat},{e.lon}"))
        for good, msg in checks:
            total += 1
            if good:
                ok += 1
            else:
                misses.append(f"{c['text'][:50]}... {msg}")
    acc = ok / total if total else 1.0
    return ("Text extractor (field accuracy)", (acc, acc, acc), (ok, total - ok, 0, 0), misses)


# ----------------------------------------------------------------- anomaly
def eval_anomaly():
    tp = fp = fn = 0
    misses = []
    for c in LABELS["anomaly"]:
        d = tempfile.mkdtemp()
        vs = VesselState(d + "/v.json", 20)
        mmsi = c.get("mmsi", 111)
        for sog, cog, _ in c["track"]:
            vs.update([{"mmsi": mmsi, "lat": 41.0, "lon": 29.0, "sog": sog, "cog": cog,
                        "nav_status": 0, "type_code": c.get("type_code")}])
        lt = c["latest"]
        pos = [{"mmsi": mmsi, "lat": 41.0, "lon": 29.0, "sog": lt["sog"],
                "cog": c["track"][-1][1], "nav_status": lt["nav_status"],
                "type_code": c.get("type_code")}]
        vs.update(pos)
        got = {a.kind for a in detect(vs, pos, CFG_ANOM, {str(mmsi)})}
        exp = set(c["expect"])
        tp += len(got & exp)
        fp += len(got - exp)
        fn += len(exp - got)
        if got != exp:
            misses.append(f"{c['name']}: got {sorted(got)} exp {sorted(exp)}")
    return ("AIS anomaly rules", _prf(tp, fp, fn), (tp, fp, fn, 0), misses)


def main():
    sections = [eval_news(), eval_extract(), eval_anomaly()]
    lines = ["# Eval report", "",
             f"_generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} · "
             f"`py eval/run_eval.py`_", "",
             "| Bileşen | Precision | Recall | F1 | TP | FP | FN |",
             "| :-- | --: | --: | --: | --: | --: | --: |"]
    worst_f1 = 1.0
    for name, (p, r, f), (tp, fp, fn, _tn), _m in sections:
        lines.append(f"| {name} | {p:.2f} | {r:.2f} | {f:.2f} | {tp} | {fp} | {fn} |")
        worst_f1 = min(worst_f1, f)
    for name, _scores, _cnt, misses in sections:
        if misses:
            lines += ["", f"### {name} — kaçırılanlar"]
            lines += [f"- {m}" for m in misses]
    lines += ["", "> Sentetik + az sayıda örnek; mutlak sayı değil, regresyon takibi için."]
    (Path(__file__).parent / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if worst_f1 >= 0.6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
