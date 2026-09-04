"""Age out stale warnings and auto-close old incidents.

A live feed must not keep yesterday's storm warning or a week-old red dot on the
map. Also drops the bundled demo seeds once real data has arrived.
"""

from __future__ import annotations

import re
import time

from .dedup import _epoch

# phrases that mean the situation is over (not just "rescued", which is also how
# an incident is first reported)
_RESOLVED_RE = re.compile(
    r"tamamland|sona er|sonuçland|sağ salim|yara almadan|"
    r"limana (getiril|çekil|ulaş)|karaya (çıkarıl|alın)|operasyon.*son",
    re.IGNORECASE,
)

# how long a warning stays "active" after its last update, by kind (hours)
_WARN_TTL_H = {
    "marine-weather": 18, "metar": 18, "earthquake": 48,
    "nav-warning": 72, "navtex": 72, "gdacs": 72, "eonet": 72,
}
# no update for this long -> signal deleted, probable/confirmed marked resolved
_INC_RESOLVE_H = {"signal": 12, "probable": 36, "confirmed": 72}
_HISTORY_H = 24 * 7  # keep resolved/false-positive incidents this long


def _age_h(ts: str | None):
    e = _epoch(ts)
    return None if e is None else (time.time() - e) / 3600.0


def prune(store) -> tuple[int, int]:
    real_inc = any("seed" not in i for i in store.incidents)
    real_w = any("seed" not in w for w in store.warnings)
    dropped_w = dropped_i = 0

    for wid, w in list(store.warnings.items()):
        age = _age_h(w.last_update or w.issued)
        expired = age is not None and age > _WARN_TTL_H.get(w.kind, 48)
        if ("seed" in wid and real_w) or expired:
            del store.warnings[wid]
            dropped_w += 1

    for iid, inc in list(store.incidents.items()):
        if "seed" in iid and real_inc:
            del store.incidents[iid]
            dropped_i += 1
            continue

        age = _age_h(inc.last_update)
        if inc.status in ("resolved", "false-positive"):
            if age is not None and age > _HISTORY_H:
                del store.incidents[iid]
                dropped_i += 1
            continue

        # an official source now says it is over -> close it, whatever the age
        if any(s.kind == "official" and _RESOLVED_RE.search(s.detail or "") for s in inc.sources):
            inc.status = "resolved"
            inc.notes.append("resmi kaynak olayın sonuçlandığını bildirdi")
            dropped_i += 1
            continue

        if age is None:
            continue
        limit = _INC_RESOLVE_H.get(inc.status)
        if limit and age > limit:
            if inc.status == "signal":
                del store.incidents[iid]
                dropped_i += 1
            else:
                inc.status = "resolved"
                inc.notes.append(f"otomatik kapandı: ~{age:.0f} saat güncelleme yok")
    return dropped_w, dropped_i
