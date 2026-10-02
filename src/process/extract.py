"""Pull structured facts out of Turkish incident text (news headlines, official
statements): vessel name, coordinates, casualty and rescued counts, place names.

Rules + a gazetteer, no ML dependency. Conservative: it would rather return
nothing than a wrong guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..geo import area_of
from .classify import PLACE_HINTS, _norm

# vessel-type word + any Turkish case suffix (gemisi, gemisinin, teknesiyle, ...)
_VW = r"(?:gemi|tekne|şile[pb]|yat|kotra|feribot|römorkör|tanker|balıkçı\s+teknesi|sürat\s+teknesi)\w*"

# "ALSU gemisi" / "Alsu isimli tekne" / 'Alsu' gemisi / “Alsu” gemi
_VESSEL_RE = [
    re.compile(
        r"[«\"'“]([A-Za-zÇĞİÖŞÜçğıöşü][\wÇĞİÖŞÜçğıöşü .-]{1,28}?)[»\"'”]\s*(?:isimli\s+|adlı\s+)?" + _VW,
        re.IGNORECASE,
    ),
    re.compile(r"\b([A-ZÇĞİÖŞÜ][A-Za-z0-9ÇĞİÖŞÜçğıöşü .-]{2,26}?)\s+(?:isimli|adlı)\s+" + _VW),
    re.compile(r"\b([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9]{1,}(?:[ .-][A-ZÇĞİÖŞÜ0-9]{1,}){0,3})\s+" + _VW),
]

# What happened to a counted group of people is read from the first such word
# after the count (the first, so "2 kişi kayıp, tekne kurtarıldı" stays missing).
# Harmed / missing / still at risk -> casualties:
_HARM_KW = (
    r"kayıp|kayb"  # kayıp, kayboldu, hayatını kaybetti, can kaybı
    r"|yaral"  # yaralı, yaralandı
    r"|öl(?!ç)"  # öldü, ölü, ölüm (not ölçüm)
    r"|boğul"  # boğuldu
    r"|ces[ae][dt]"  # ceset, cesedi
    r"|mahsur"  # mahsur kaldı
    r"|aran"  # aranıyor, aranan
    r"|arama\s+çalışma"  # "10 denizciyi arama çalışmaları" (not "arama kurtarma")
    r"|kurtarılama"  # kurtarılamadı: could not be saved (tried before the rescue words)
)
# ... rescued / evacuated -> rescued. Only a completed rescue: "kurtarma" alone is
# the operation ("arama kurtarma botu"), not an outcome, so it says nothing.
_RESCUE_KW = r"kurtar(?:ıl|d|mış)|tahliye\s+e(?:dil|tt|tmiş)"
_OUTCOME_RE = re.compile(r"\b(?:(?P<harm>" + _HARM_KW + r")|(?P<rescue>" + _RESCUE_KW + r"))", re.IGNORECASE)
_REACH = 40  # how far after the count the outcome word may start (as before the split)
# with no word after the count, one right before it: "Kayıp 10 denizci nerede?"
_PRE_KW = r"kayıp|kaybolan|aranan|mahsur\s+kalan"

_PEOPLE_RE = re.compile(
    r"(?:\b(?P<pre>" + _PRE_KW + r")\s+)?"
    # not the tail of a longer number ("1.500", "2026")
    r"(?<![\d.,])(?P<n>\d{1,3})\s*(?:[a-zçğıöşü]+\s+){0,2}?"  # optional adjectives ("20 düzensiz göçmen")
    r"(?:kişi|şahıs|can|mürettebat|göçmen|çocuk|yolcu|denizci|balıkçı(?!\s+tekne)|tayfa|personel)"
    r"(?!l[iı]k)"  # "5 kişilik tekne" is a capacity, not people
    # Coast Guard style "18 Düzensiz Göçmen (Beraberinde 1 Çocuk) Kurtarılmıştır"
    r"(?P<aside>\s*\([^()]{0,40}\))?"
    # what follows, up to a full stop or the next number, so a word belongs to the
    # nearest count before it ("2 kişi kurtarıldı, 1 balıkçı kayıp"). A lookahead,
    # so a "kayıp" in it can still prefix the next count.
    r"(?=(?P<ctx>[^.\d]{0,60}))",
    re.IGNORECASE,
)

# 40°55'K 28°10'D   |   40 55 12 N 28 10 30 E   |   40.912 N, 28.241 E   |   40.91, 28.24
_DMS_RE = re.compile(
    r"(\d{1,2})[°º:\s]\s*(\d{1,2})(?:['′\s]\s*(\d{1,2}(?:\.\d+)?)?[\"″]?)?\s*([KNGSkngs])"
    r"[,;\s/]+(\d{1,3})[°º:\s]\s*(\d{1,2})(?:['′\s]\s*(\d{1,2}(?:\.\d+)?)?[\"″]?)?\s*([DEBWdebw])"
)
_DEC_RE = re.compile(r"(-?\d{1,2}\.\d{2,6})\s*([KNkn])?\s*[,;\s]+\s*(-?\d{1,3}\.\d{2,6})\s*([DEde])?")

_TR_BBOX = (34.0, 44.0, 24.0, 43.0)  # lat_min, lat_max, lon_min, lon_max


# incident type inferred from the wording, most specific first
_TYPE_RULES = [
    ("collision", r"çarpış|çatış|çarptı"),
    ("grounding", r"karaya otur|karaya vur|sığlığa"),
    ("capsize", r"alabora|ters dön|yan yattı|devril"),
    ("sinking", r"batt[ıi]|batan|batık|bat[ıi]yor|su ald[ıi]|su al[ıi]yor"),
    ("fire", r"yangın|alev|yandı"),
    ("man-overboard", r"denize düş|adam düş|denize atla"),
    ("drift", r"sürüklen|makine arıza|kumanda dışı|motor arıza"),
    ("distress", r"imdat|mayday|tehlike çağrısı|yardım çağrısı"),
    # a completed rescue is not a distress call; the channel used to announce
    # "2 sahis kurtarilmistir" as "tehlike cagrisi"
    ("rescue", r"kurtarıld|kurtarılmış|kurtarıl(dı|mak)|sağ salim|karaya çıkarıl"),
    ("distress", r"kurtarma|mahsur|tahliye|arama kurtarma|kayb?ol"),
]


def incident_type(text: str) -> str:
    """Map Turkish incident wording to an IncidentType value."""
    low = _norm(text)
    for name, pattern in _TYPE_RULES:
        if re.search(pattern, low):
            return name
    return "unknown"


@dataclass
class Extracted:
    vessel: str | None = None
    lat: float | None = None
    lon: float | None = None
    area: str = ""
    casualties: int | None = None  # harmed / missing / at risk
    rescued: int | None = None  # rescued / evacuated
    places: list[str] = field(default_factory=list)
    itype: str = "unknown"
    precise: bool = False  # True when real coordinates were parsed, not a city name


def _in_tr(lat, lon) -> bool:
    a, b, c, d = _TR_BBOX
    return a <= lat <= b and c <= lon <= d


def _dms(d, m, s, hemi) -> float:
    val = float(d) + float(m) / 60 + (float(s) if s else 0) / 3600
    return -val if hemi.upper() in ("G", "S", "B", "W") else val


def coordinates(text: str):
    m = _DMS_RE.search(text)
    if m:
        lat = _dms(m.group(1), m.group(2), m.group(3), m.group(4))
        lon = _dms(m.group(5), m.group(6), m.group(7), m.group(8))
        if _in_tr(lat, lon):
            return round(lat, 4), round(lon, 4)
    m = _DEC_RE.search(text)
    if m:
        lat = float(m.group(1))
        lon = float(m.group(3))
        if (m.group(2) or "").upper() in ("", "K", "N") and _in_tr(lat, lon):
            return round(lat, 4), round(lon, 4)
    return None, None


def vessel_name(text: str):
    stop = {
        "SAHİL",
        "SAHIL",
        "GÜVENLİK",
        "GUVENLIK",
        "KURTARMA",
        "ARAMA",
        "DENİZ",
        "DENIZ",
        "SON",
        "DAKİKA",
        "DAKIKA",
        "HABERİ",
        "HABERI",
        "TÜRK",
        "TURK",
    }
    for rx in _VESSEL_RE:
        for m in rx.finditer(text):
            name = " ".join(m.group(1).split()).strip(" .,-")
            words = name.upper().split()
            if 1 <= len(words) <= 4 and not any(w in stop for w in words) and len(name) >= 3:
                return name
    return None


def _outcome(m):
    """The first outcome word (harm or rescue) after a people count, or None."""
    aside = _OUTCOME_RE.search(m.group("aside") or "")
    if aside and aside.group("harm"):
        return aside  # "(2'si ölü)" must not be skipped over into a rescue
    word = _OUTCOME_RE.search(m.group("ctx"))
    return word if word is not None and word.start() <= _REACH else None


def people_counts(text: str):
    """(casualties, rescued) named in text, each None when the text gives no count.

    A count with neither kind of word after it, nor "kayıp"/"aranan" right
    before it ("teknedeki 4 kişi", "23 göçmen yakalandı") goes to neither: it may
    be a crew that is fine, the passengers, or the people later rescued, and
    calling it casualties would turn a routine report critical.
    Several counts of one kind -> the largest: outlets repeat the same figure and
    backfill reads all sources of an incident together, so adding double counts.
    """
    harmed = rescued = None
    for m in _PEOPLE_RE.finditer(text):
        n = int(m.group("n"))
        if n > 500:
            continue
        word = _outcome(m)
        if word is not None and word.group("rescue"):
            rescued = max(n, rescued or 0)
        elif word is not None or m.group("pre"):
            harmed = max(n, harmed or 0)
    return harmed, rescued


def misread_rescue(stored_casualties, text_casualties, text_rescued) -> bool:
    """True when a casualty count stored before `rescued` existed is really the
    rescue count: the extractor used to take the first count in a headline, so
    "34 Düzensiz Göçmen Kurtarılmıştır" was kept as 34 casualties (critical).
    Only an exact match with what the same text now reads as rescued counts."""
    return stored_casualties is not None and text_rescued == stored_casualties != text_casualties


def places(text: str):
    low = _norm(text)
    hits = []
    for name, (lat, lon) in PLACE_HINTS.items():
        if _norm(name) in low and name.title() not in hits:
            hits.append((name.title(), lat, lon))
    return hits


def extract(text: str) -> Extracted:
    e = Extracted()
    e.vessel = vessel_name(text)
    e.casualties, e.rescued = people_counts(text)
    lat, lon = coordinates(text)
    pl = places(text)
    e.places = [p[0] for p in pl]
    if lat is not None:
        e.lat, e.lon, e.precise = lat, lon, True
    elif pl:
        e.lat, e.lon = pl[0][1], pl[0][2]
    e.area = area_of(e.lat, e.lon)
    e.itype = incident_type(text)
    return e
