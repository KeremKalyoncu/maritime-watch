"""Age out stale warnings and auto-close old incidents.

A live feed must not keep yesterday's storm warning or a week-old red dot on the
map. Also drops the bundled demo seeds once real data has arrived.
"""

from __future__ import annotations

import re
import time

from ..model import fix_mojibake
from .dedup import _epoch
from .extract import extract
from .privacy import drop_aftermath, redact

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


def scrub_names(store) -> int:
    """Redact person names, and repair mis-decoded text, already in the store.

    New records are cleaned at ingest, but web/data/incidents.json is committed
    and carried between runs, so anything stored before that guard existed - and
    anything a future feed sneaks in - has to be cleaned here as well.
    """
    n = 0
    for inc in store.incidents.values():
        keep = (inc.vessel.name,) if inc.vessel.name else ()
        for s in inc.sources:
            cleaned = redact(fix_mojibake(s.detail or ""), keep=keep)
            if cleaned != s.detail:
                s.detail = cleaned
                n += 1
    return n


def backfill(store) -> int:
    """Re-read stored headlines with the current extractor.

    An incident keeps whatever the parser understood on the day it arrived, so a
    report taken in before the extractor learned a place name still shows up as
    "Ne oldu: belirsiz" with no pin - and it never comes back through ingest once
    the source page has moved on. Only empty fields are filled; anything a later
    official update set is left alone.
    """
    n = 0
    for inc in store.incidents.values():
        text = " ".join(s.detail for s in inc.sources if s.kind in ("official", "news") and s.detail)
        if not text:
            continue
        ex = extract(text)
        # the extractor owns the text-derived type; an AIS-driven record keeps
        # the type its anomaly set
        from_ais = any(s.kind.startswith("ais") for s in inc.sources)
        if not from_ais and ex.itype != "unknown" and inc.type != ex.itype:
            inc.type, n = ex.itype, n + 1
        for attr, val in (("area", ex.area),
                          ("lat", ex.lat), ("lon", ex.lon), ("casualties", ex.casualties)):
            cur = getattr(inc, attr)
            if val and not cur:
                setattr(inc, attr, val)
                n += 1
        if ex.places and not inc.places:
            inc.places = ex.places
        if ex.vessel and not inc.vessel.name:
            inc.vessel.name = ex.vessel
    return n


_TR_LOWER = str.maketrans("İIŞĞÜÖÇ", "iışğüöç")


def drop_stored_aftermath(store, cfg: dict | None) -> int:
    """The aftermath filter runs at ingest, but the store is committed and carried
    forward, so funeral and courtroom items taken in earlier keep sitting on the
    map. Re-apply the same test to what is already there."""
    words = [w.translate(_TR_LOWER).lower() for w in (cfg or {}).get("news", {}).get("aftermath_words", [])]
    if not words:
        return 0
    n = 0
    for iid, inc in list(store.incidents.items()):
        srcs = [s for s in inc.sources if s.kind == "news"]
        if not srcs or len(srcs) != len(inc.sources):
            continue                       # an official source keeps it alive
        if all(drop_aftermath(s.detail.translate(_TR_LOWER).lower(), words) for s in srcs):
            del store.incidents[iid]
            n += 1
    return n


# weather kinds whose absence from a live feed means the hazard is over
_LIVE_WX = ("marine-weather", "metar")


def clear_passed_weather(store, seen_ids: set[str], live_sources: bool) -> list:
    """Close weather warnings the source no longer reports.

    A gale warning used to sit on the channel for its full 18-hour TTL even after
    the wind dropped, so nobody learned it was over and the next one got ignored.
    If the forecast came back live this cycle and no longer lists the area, the
    warning has passed. Only when the fetch was live - a dead source must not be
    read as "all clear".
    """
    if not live_sources:
        return []
    gone = []
    for wid, w in list(store.warnings.items()):
        if w.kind in _LIVE_WX and wid not in seen_ids:
            gone.append(w)
            del store.warnings[wid]
    return gone


def dedupe_sources(store) -> int:
    """Drop repeated sources on one incident.

    add_source() refuses a duplicate, but correlation paths that append straight
    to the list do not, so the same outlet's headline could be listed twice and
    the message would count it as two confirmations.
    """
    n = 0
    for inc in store.incidents.values():
        seen, keep = set(), []
        for s in inc.sources:
            k = s.key()
            if k in seen:
                n += 1
                continue
            seen.add(k)
            keep.append(s)
        inc.sources = keep
    return n


def unmerge_legacy_reports(store) -> int:
    """Undo merges made before correlation learned to keep announcements apart.

    Five separate Izmir rescues, five days apart, had collapsed into one record
    and the message added their casualty counts together ("30 kisi bildirildi").
    A scraped report's id is the sha1 of its own headline, so any other official
    source on that record does not belong to it; each of those already exists, or
    comes back, as its own incident.
    """
    import hashlib

    from ..ingest.official import _norm as _onorm
    n = 0
    for iid, inc in store.incidents.items():
        if not iid.startswith("rep-"):
            continue
        want = iid[len("rep-"):]
        official = [s for s in inc.sources if s.kind == "official"]
        if len(official) < 2:
            continue
        keep = [s for s in official
                if hashlib.sha1(_onorm(s.detail or "").encode("utf-8")).hexdigest().startswith(want)]
        if not keep or len(keep) == len(official):
            continue
        inc.sources = keep + [s for s in inc.sources if s.kind != "official"]
        inc.casualties = None          # recomputed by backfill from what is left
        inc.type = "unknown"
        inc.vessel.name = None
        n += len(official) - len(keep)
    return n


def prune(store, cfg: dict | None = None) -> tuple[int, int]:
    scrub_names(store)
    unmerge_legacy_reports(store)
    dedupe_sources(store)
    backfill(store)
    dropped_aftermath = drop_stored_aftermath(store, cfg)
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
    return dropped_w, dropped_i + dropped_aftermath
