"""Turkish news RSS, keyword filtered.

A headline is kept only if it contains one maritime word and one incident word.
These become low-weight `news` sources: on their own they stay at `signal`, but
when they sit near an AIS anomaly the correlation step lifts the incident to
`probable`.
"""

from __future__ import annotations

import re
import time
from xml.etree import ElementTree as ET

from ..model import Incident, Source, Vessel, stable_hash
from ..process.extract import extract
from ..process.privacy import drop_aftermath, redact
from ._net import fetch_parallel

_TR_LOWER = str.maketrans("İIŞĞÜÖÇ", "iışğüöç")


def _norm(s: str) -> str:
    return s.translate(_TR_LOWER).lower()


def _match(text_low: str, tokens: list[str], keywords: list[str]) -> bool:
    """A keyword matches if it is a phrase found in the text, an exact token, or
    (for words of 4+ letters) a token prefix so Turkish suffixes still match."""
    for kw in keywords:
        if " " in kw:
            if kw in text_low:
                return True
        elif kw in tokens or len(kw) >= 4 and any(t.startswith(kw) for t in tokens):
            return True
    return False


def _parse_rss(xml_text: str) -> list[tuple[str, str, str]]:
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title:
            out.append((title, link, pub))
    return out


def _recent(pubdate: str, hours_back: int) -> bool:
    if not pubdate:
        return True
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            t = time.strptime(pubdate.strip(), fmt)
            return (time.time() - time.mktime(t)) <= hours_back * 3600 + 7200
        except ValueError:
            continue
    return True


def fetch_news(cfg: dict) -> list[Incident]:
    nc = cfg["news"]
    mari = [_norm(w) for w in nc["maritime_words"]]
    inci = [_norm(w) for w in nc["incident_words"]]
    after = [_norm(w) for w in nc.get("aftermath_words", [])]
    never = [_norm(w) for w in nc.get("exclude_words", [])]
    out: list[Incident] = []
    seen: set[str] = set()

    tasks = [(feed, f"news_{i}.xml", None, 15) for i, feed in enumerate(nc["feeds"])]
    results = fetch_parallel(tasks, max_workers=6)
    for (feed, _sample, _hdr, _to), (raw, _live) in zip(tasks, results, strict=False):
        if not raw:
            continue
        for title, link, pub in _parse_rss(raw)[: nc["max_items_per_feed"]]:
            low = _norm(title)
            tokens = re.findall(r"[a-zçğıöşü]+", low)
            if not (_match(low, tokens, mari) and _match(low, tokens, inci)):
                continue
            if drop_aftermath(low, after):
                continue          # funerals, arrests and hearings warn nobody
            if drop_aftermath(low, never):
                continue          # a diving accident off a jetty is not a sea incident
            if not _recent(pub, nc["hours_back"]):
                continue
            key = low[:80]
            if key in seen:
                continue
            seen.add(key)

            ex = extract(title)
            inc = Incident(
                id="news-" + stable_hash(key, 10),   # content, not date: see official.py
                type=ex.itype, lat=ex.lat, lon=ex.lon, area=ex.area,
                casualties=ex.casualties, places=ex.places,
                coarse=not ex.precise,
                vessel=Vessel(name=ex.vessel) if ex.vessel else Vessel(),
            )
            inc.sources.append(Source(kind="news", org=_host(feed),
                                      detail=redact(title, keep=(ex.vessel,)), url=link))
            out.append(inc)
    return out[:20]


def _host(url: str) -> str:
    return url.split("//")[-1].split("/")[0].replace("www.", "")
