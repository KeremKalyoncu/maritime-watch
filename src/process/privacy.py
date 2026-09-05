"""Keep named individuals out of what we publish.

The mission is warning mariners about live hazards, so victim identities, their
relatives and the judicial aftermath add nothing operational - but they are
personal data, they go to a public channel, and the git history of this repo
keeps them for good. Two layers:

  drop_aftermath()  a funeral / arrest / court headline is not a hazard warning
  redact()          for anything that still gets through, blank the person name

Vessel names survive both: a ship called "Tuğberk İmamoğlu" reads exactly like a
person, and losing it would break correlation, so the caller passes it in `keep`.
"""

from __future__ import annotations

import re

from .classify import PLACE_HINTS

_TR_LOWER = str.maketrans("İIŞĞÜÖÇ", "iışğüöç")


def _norm(s: str) -> str:
    return s.translate(_TR_LOWER).lower()


# Turkish possessive/case suffix after an apostrophe: 'in 'nin 'nın 'un 'e 'a
# 'den 'dan 'yi 'ye. A proper noun carrying one is almost always a person or a
# place, and places are filtered out below.
_SUFFIX = r"['’\u2019](?:n?[ıiuü]n|n?[ae]|[dt][ae]n?|y?[ıiuü])\b"

# a victim named by one word only: "hayatını kaybeden Demir'in cenazesi"
_VICTIM_CONTEXT = re.compile(
    r"(?:hayatını kaybeden|yaşamını yitiren|vefat eden|ölen|boğulan|kaybolan|"
    r"cansız bedeni bulunan|kayıp)\s+"
    r"([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})?)")

# "Ad Soyad'ın", and "Ad Soyad" standing right before a kinship word
_NAMED_POSSESSIVE = re.compile(
    r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})\s+([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})(?=" + _SUFFIX + r")")
_NAMED_KIN = re.compile(
    r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})\s+([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})"
    r"(?=\s+(?:eşi|eşinin|babası|annesi|oğlu|kızı|kardeşi|ailesi|yakını|yakınları))")

# capitalised words that are geography or maritime vocabulary, never a person
_NOT_A_PERSON = set(PLACE_HINTS) | {_norm(w) for w in ["Denizi", "Deniz", "Boğazı", "Boğaz", "Körfezi", "Körfez", "Adası", "Ada", "Adaları", "Limanı", "Liman", "İskelesi", "Burnu", "Koyu", "Açıkları", "Açıklarında", "Önlerinde", "Sahil", "Güvenlik", "Komutanlığı", "Bakanlığı", "Valiliği", "Belediyesi", "Başkanlığı", "Müdürlüğü", "Kurumu", "Gemisi", "Gemileri", "Gemi", "Teknesi", "Tekne", "Feribotu", "Vapuru", "Kaptanı", "Mürettebat", "Türkiye", "Kıbrıs", "Yunanistan", "Bulgaristan", "Romanya", "Ukrayna", "Rusya", "Gürcistan"]}

REDACTED = "[isim]"


def _is_person(a: str, b: str, keep_norm: set[str]) -> bool:
    if _norm(f"{a} {b}") in keep_norm or _norm(a) in keep_norm or _norm(b) in keep_norm:
        return False
    return _norm(a) not in _NOT_A_PERSON and _norm(b) not in _NOT_A_PERSON


def redact(text: str, keep: tuple[str, ...] = ()) -> str:
    """Replace personal names with a marker. `keep` holds vessel names, which
    look identical to person names in Turkish headlines."""
    if not text:
        return text
    keep_norm = {_norm(k) for k in keep if k}
    keep_norm |= {w for k in keep if k for w in _norm(k).split()}

    def sub(m: re.Match) -> str:
        return REDACTED if _is_person(m.group(1), m.group(2), keep_norm) else m.group(0)

    def sub1(m: re.Match) -> str:
        parts = m.group(1).split()
        head = m.group(0)[:m.start(1) - m.start(0)]
        if len(parts) == 2 and not _is_person(parts[0], parts[1], keep_norm):
            return m.group(0)
        if len(parts) == 1 and (_norm(parts[0]) in _NOT_A_PERSON or _norm(parts[0]) in keep_norm):
            return m.group(0)
        return head + REDACTED

    text = _VICTIM_CONTEXT.sub(sub1, text)
    for rx in (_NAMED_POSSESSIVE, _NAMED_KIN):
        text = rx.sub(sub, text)
    return text


def drop_aftermath(text_low: str, words: list[str]) -> bool:
    """True when the headline is about the aftermath (funeral, arrest, hearing)
    rather than a hazard anyone can still act on."""
    tokens = re.findall(r"[a-zçğıöşü]+", text_low)
    for kw in words:
        if " " in kw:
            if kw in text_low:
                return True
        elif kw in tokens or len(kw) >= 4 and any(t.startswith(kw) for t in tokens):
            return True
    return False
