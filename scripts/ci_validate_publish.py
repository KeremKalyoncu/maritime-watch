"""Validate published web/data artifacts before they land on Pages.

Used by the Actions cycle after ``run.py --once``. Fail closed on integrity
problems (sample leak fingerprints, broken schema); soft-skip when a source
was legitimately empty this cycle.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "web" / "data"

# Known fixture fingerprints from the live-channel incident (see test_no_fixture_leak)
_FORBIDDEN_SNIPPETS = (
    "dalga ~2.7 m",
    "ruzgar hamlesi ~41 kn",
    "rüzgâr hamlesi ~41 kn",
)

BOAT_CLASSES = ("small", "medium", "large")
WINDOW_LEVELS = frozenset({"ok", "watch", "danger", "unknown"})


def _load(name: str) -> object | None:
    path = WEB_DATA / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8") or "null")
    except json.JSONDecodeError as e:
        raise SystemExit(f"[validate] {name}: invalid JSON ({e})") from e


def _scan_forbidden(label: str, blob: object) -> None:
    raw = json.dumps(blob, ensure_ascii=False)
    for snip in _FORBIDDEN_SNIPPETS:
        if snip in raw:
            raise SystemExit(f"[validate] {label}: forbidden fixture fingerprint {snip!r}")


def validate_outlook(data: object | None) -> list[str]:
    notes: list[str] = []
    if data is None:
        notes.append("outlook.json missing (soft) — cycle may have skipped write")
        return notes
    if not isinstance(data, dict):
        raise SystemExit("[validate] outlook.json: expected object")
    if data.get("schema_version") != 1:
        raise SystemExit("[validate] outlook.json: schema_version must be 1")
    if not data.get("generated"):
        raise SystemExit("[validate] outlook.json: missing generated")
    classes = data.get("classes")
    if not isinstance(classes, dict):
        raise SystemExit("[validate] outlook.json: missing classes")
    for cid in BOAT_CLASSES:
        if cid not in classes:
            raise SystemExit(f"[validate] outlook.json: missing class {cid}")
        areas = (classes[cid] or {}).get("areas")
        if not isinstance(areas, list):
            raise SystemExit(f"[validate] outlook.json: {cid}.areas must be list")
        for a in areas:
            for w in a.get("windows") or []:
                lv = w.get("level")
                if lv not in WINDOW_LEVELS:
                    raise SystemExit(f"[validate] outlook bad window level {lv!r}")
    cov = data.get("coverage")
    if isinstance(cov, dict):
        present = int(cov.get("present") or 0)
        expected = int(cov.get("expected") or 0)
        missing = cov.get("missing") or []
        notes.append(f"outlook coverage {present}/{expected} missing={len(missing)}")
        if expected > 0 and present == 0:
            raise SystemExit("[validate] outlook.json: expected areas but present=0")
    else:
        notes.append("outlook coverage field absent (older schema)")
    _scan_forbidden("outlook.json", data)
    return notes


def validate_safety(data: object | None) -> list[str]:
    notes: list[str] = []
    if data is None:
        notes.append("safety_index.json missing (soft)")
        return notes
    if not isinstance(data, dict):
        raise SystemExit("[validate] safety_index.json: expected object")
    ratings = data.get("ratings")
    if not isinstance(ratings, list):
        raise SystemExit("[validate] safety_index.json: ratings must be list")
    for r in ratings:
        if not isinstance(r, dict):
            continue
        q = r.get("data_quality")
        score = r.get("score")
        # unknown quality must not look like a confident green 100
        if q == "unknown" and isinstance(score, (int, float)) and score >= 95:
            raise SystemExit(
                f"[validate] safety_index: unknown quality with score={score} "
                f"area={r.get('area')!r}"
            )
    _scan_forbidden("safety_index.json", data)
    notes.append(f"safety ratings={len(ratings)}")
    return notes


def validate_health(data: object | None) -> list[str]:
    notes: list[str] = []
    if data is None:
        notes.append("health.json missing (soft)")
        return notes
    if not isinstance(data, dict):
        raise SystemExit("[validate] health.json: expected object")
    # write_health stores per-file fetch outcomes under "fetch"
    status = data.get("fetch") or data.get("fetch_status") or {}
    if isinstance(status, dict):
        samples = [k for k, v in status.items() if v == "sample"]
        if samples:
            raise SystemExit(
                f"[validate] health.json: sample-backed sources would publish: {samples}"
            )
    notes.append("health ok")
    return notes


def validate_warnings(data: object | None) -> list[str]:
    if data is None:
        return ["warnings.json missing (soft)"]
    if isinstance(data, list):
        return [f"warnings={len(data)}"]
    if isinstance(data, dict) and isinstance(data.get("warnings"), list):
        return [f"warnings={len(data['warnings'])}"]
    raise SystemExit("[validate] warnings.json: unexpected shape")


def main() -> int:
    notes: list[str] = []
    notes += validate_outlook(_load("outlook.json"))
    notes += validate_safety(_load("safety_index.json"))
    notes += validate_health(_load("health.json"))
    notes += validate_warnings(_load("warnings.json"))
    for n in notes:
        print(f"[validate] {n}")
    print("[validate] publish artifacts OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
