"""Scraper for Kıyı Emniyeti Genel Müdürlüğü (KEGM) rescue operations and incidents.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..model import Incident, Source, Vessel
from ..process.extract import extract
from ..process.privacy import redact
from ._net import get_text
from .official import _collapse_dup, _kw_hit, _norm

_fetch = get_text

KEGM_DEFAULT_URL = "https://www.kiyiemniyeti.gov.tr/kurtarma_operasyonlari"
KEGM_BASE_URL = "https://www.kiyiemniyeti.gov.tr"
KEGM_KEYWORDS = [
    "kurtar", "yedekle", "karaya", "su alan", "yangın", "sürüklen",
    "çatışma", "tahliye", "arıza", "yardım", "mahsur", "kaza",
]


def scrape_kegm(cfg: dict | None = None) -> list[Incident]:
    """Scrape KEGM rescue and assistance operations."""
    cfg = cfg or {}
    url = cfg.get("scrape", {}).get("kegm_url", KEGM_DEFAULT_URL)
    raw, _live = _fetch(url, "kegm_sample.html")
    out: list[Incident] = []
    if not raw:
        return out

    soup = BeautifulSoup(raw, "html.parser")
    host = urlparse(KEGM_BASE_URL).netloc
    seen_titles: set[str] = set()

    # Find anchor links in articles or lists
    for a in soup.find_all("a", href=True):
        title = _collapse_dup(" ".join(a.get_text(" ", strip=True).split()))
        if not _kw_hit(title, KEGM_KEYWORDS):
            continue

        ex = extract(title)
        has_signal = bool(re.search(r"\d", title)) or ex.lat is not None or ex.vessel
        if len(title) < 25 or not has_signal:
            continue

        href = urljoin(KEGM_BASE_URL + "/", a["href"])
        pu = urlparse(href)
        if pu.netloc and host not in pu.netloc:
            continue

        norm = _norm(title)
        if norm in seen_titles:
            continue
        seen_titles.add(norm)

        inc_id = "kegm-" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:10]
        inc = Incident(
            id=inc_id,
            type=ex.itype,
            lat=ex.lat,
            lon=ex.lon,
            area=ex.area,
            casualties=ex.casualties,
            places=ex.places,
            coarse=not ex.precise,
            vessel=Vessel(name=ex.vessel) if ex.vessel else Vessel(),
        )
        inc.sources.append(Source(
            kind="official",
            org="Kıyı Emniyeti Genel Müdürlüğü",
            detail=redact(title, keep=(ex.vessel,)),
            url=href,
        ))
        out.append(inc)

    return out[:15]
