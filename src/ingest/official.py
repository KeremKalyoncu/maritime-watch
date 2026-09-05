"""Scrapers for official sources (MGM, Sahil Guvenlik, AFAD).

There is no stable public API, so each parser catches its own errors, logs the
failure and returns an empty list. Fetching goes through _net.get_text, so the
"never publish fixture data" rule applies here too: a Coast Guard outage must not
turn the sample file's rescue headline into a "confirmed" incident.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..model import Incident, Source, Vessel, Warning, make_id
from ..process.classify import area_centroid
from ..process.extract import extract
from ._net import get_text

# one fetch path for the whole project, so the "never publish fixture data" rule
# in _net.py applies to the scrapers too
_fetch = get_text


_TR_LOWER = str.maketrans("İIŞĞÜÖÇ", "iışğüöç")


def _norm(s: str) -> str:
    # str.lower() turns "İ" into "i̇" (i + combining dot); fix that first
    return s.translate(_TR_LOWER).lower()


def _kw_hit(text: str, keywords: list[str]) -> str | None:
    low = _norm(text)
    return next((k for k in keywords if _norm(k) in low), None)


def _collapse_dup(t: str) -> str:
    # some site templates print the headline twice: "X X" or "DATE BODY BODY"
    w = t.split()
    n = len(w)
    for k in range(0, min(n // 2 + 1, 8)):
        rest = w[k:]
        m = len(rest)
        if m >= 4 and m % 2 == 0 and rest[: m // 2] == rest[m // 2:]:
            return " ".join(w[:k] + rest[: m // 2])
    return t


def scrape_mgm_marine(cfg: dict) -> list[Warning]:
    """MGM marine forecast regions. The JSON schema is undocumented and changes."""
    url = "https://servis.mgm.gov.tr/web/denizler/tahmin/bolgeler"
    raw, _live = _fetch(url, "mgm_marine.json",
                        headers={"Origin": "https://www.mgm.gov.tr", "Referer": "https://www.mgm.gov.tr/"})
    out: list[Warning] = []
    if not raw:
        return out
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("[scrape] mgm: response was not JSON (site changed?)")
        return out

    rows = data if isinstance(data, list) else data.get("result") or data.get("bolgeler") or []
    for row in rows or []:
        name = row.get("bolge") or row.get("name") or row.get("Bolge") or ""
        wind = str(row.get("ruzgarHiz") or row.get("wind") or row.get("ruzgar") or "")
        warn = str(row.get("uyari") or row.get("hadise") or row.get("warning") or "")
        text = f"{wind} {warn}".strip()
        if not name:
            continue
        # treat force 6+ Bft, or a gale keyword, as a real warning
        forces = [int(n) for n in re.findall(r"\b(\d{1,2})\b", wind)]
        strong = (any(f >= 6 for f in forces)
                  or any(w in text.lower() for w in ("fırtına", "kuvvetli", "storm", "gale")))
        if not (warn or strong):
            continue
        clat, clon = area_centroid(name)
        out.append(Warning(
            id="wx-mgm-" + re.sub(r"\W+", "", name).lower()[:24],
            headline=f"{name}: {text or 'denizcilik uyarısı'}",
            area=name,
            kind="marine-weather",
            severity="major" if strong else "minor",
            org="Meteoroloji Genel Müdürlüğü",
            url="https://www.mgm.gov.tr/denizcilik/deniz-hava-tahmini.aspx",
            raw=json.dumps(row, ensure_ascii=False)[:500],
            lat=clat, lon=clon,
        ))
    return out


def _scrape_links(cfg: dict, url: str, sample: str, org: str, base: str) -> list[Incident]:
    kws = cfg["scrape"]["keywords"]
    raw, _live = _fetch(url, sample)
    out: list[Incident] = []
    if not raw:
        return out

    soup = BeautifulSoup(raw, "html.parser")
    host = base.split("//")[-1].rstrip("/")
    seen_titles: set[str] = set()
    for a in soup.find_all("a", href=True):
        title = _collapse_dup(" ".join(a.get_text(" ", strip=True).split()))
        if not _kw_hit(title, kws):
            continue
        # keep real headlines, drop nav/menu links: needs length plus a number
        # or a place name we recognise
        ex = extract(title)
        has_signal = bool(re.search(r"\d", title)) or ex.lat is not None or ex.vessel
        if len(title) < 32 or not has_signal:
            continue

        href = urljoin(base + "/", a["href"])
        pu = urlparse(href)
        if pu.netloc and host not in pu.netloc:
            continue  # off-site link
        norm = _norm(title)
        if norm in seen_titles:
            continue
        seen_titles.add(norm)

        stable = hashlib.sha1(norm.encode("utf-8")).hexdigest()[:6]
        inc = Incident(
            id=make_id("rep", ex.lat, ex.lon) + "-" + stable,
            type=ex.itype, lat=ex.lat, lon=ex.lon, area=ex.area,
            casualties=ex.casualties, places=ex.places,
            coarse=not ex.precise,
            vessel=Vessel(name=ex.vessel) if ex.vessel else Vessel(),
        )
        inc.sources.append(Source(kind="official", org=org, detail=title, url=href))
        out.append(inc)
    return out[:15]


def scrape_sahil_guvenlik(cfg: dict) -> list[Incident]:
    return _scrape_links(cfg, "https://www.sg.gov.tr/haberler", "sahil_guvenlik.html",
                         "Sahil Güvenlik Komutanlığı", "https://www.sg.gov.tr")


def scrape_afad(cfg: dict) -> list[Incident]:
    return _scrape_links(cfg, "https://www.afad.gov.tr/basin-aciklamalari", "afad.html",
                         "AFAD", "https://www.afad.gov.tr")


def gather_official(cfg: dict) -> tuple[list[Incident], list[Warning]]:
    incidents: list[Incident] = []
    warnings: list[Warning] = []
    s = cfg["scrape"]
    if not s.get("enabled", True):
        return incidents, warnings

    jobs = [
        (s.get("mgm", True), "mgm", lambda: warnings.extend(scrape_mgm_marine(cfg))),
        (s.get("sahil_guvenlik", True), "sg", lambda: incidents.extend(scrape_sahil_guvenlik(cfg))),
        (s.get("afad", True), "afad", lambda: incidents.extend(scrape_afad(cfg))),
    ]
    for enabled, name, fn in jobs:
        if not enabled:
            continue
        try:
            fn()
        except Exception as e:
            print(f"[scrape] {name} error: {e}")
    return incidents, warnings
