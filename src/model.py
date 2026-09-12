"""Data model. Two record types, Incident and Warning, loosely modelled on CAP.
Each keeps its list of sources plus a status/confidence used to flag unverified
items on the map."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

ISO = "%Y-%m-%dT%H:%M:%SZ"


# UTF-8 bytes that were decoded as latin-1: "DAKÄ°KA" instead of "DAKİKA"
_MOJIBAKE = re.compile(r"[ÃÄÅÂ][- -¿]")


def fix_mojibake(s: str) -> str:
    """Some feeds send no charset. The same headline then arrives readable on one
    run and mangled on the next, so dedup sees two stories and the map shows a
    fisherman a line of garbage."""
    if not s or not _MOJIBAKE.search(s):
        return s
    try:
        fixed = s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
    return s if "�" in fixed else fixed


def now_iso() -> str:
    return time.strftime(ISO, time.gmtime())


class IncidentType(str, Enum):
    GROUNDING = "grounding"
    COLLISION = "collision"
    COLLISION_RISK = "collision-risk"
    DRIFT = "drift"
    DISTRESS = "distress"
    CAPSIZE = "capsize"
    FIRE = "fire"
    SINKING = "sinking"
    MOB = "man-overboard"
    RESCUE = "rescue"
    UNKNOWN = "unknown"


class Status(str, Enum):
    SIGNAL = "signal"            # one weak source (e.g. AIS anomaly only)
    PROBABLE = "probable"        # corroborated but not officially confirmed
    CONFIRMED = "confirmed"      # an official body has stated it
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false-positive"


class Severity(str, Enum):
    INFO = "info"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


# plain-Turkish labels for end users (Telegram + map)
TYPE_TR = {
    "grounding": "karaya oturma", "collision": "çatışma (çarpışma)",
    "collision-risk": "çatışma riski (yakın geçiş)",
    "drift": "sürüklenme", "distress": "tehlike çağrısı", "capsize": "alabora",
    "fire": "yangın", "sinking": "batma", "man-overboard": "denize adam düştü",
    "rescue": "kurtarma operasyonu", "unknown": "belirsiz",
}
STATUS_TR = {
    "signal": "zayıf sinyal — teyit bekliyor",
    "probable": "kuvvetli ihtimal — henüz resmi teyit yok",
    "confirmed": "doğrulandı (resmi kaynak)",
    "resolved": "kapandı",
    "false-positive": "yanlış alarm",
}


def type_tr(t: str) -> str:
    return TYPE_TR.get(t, t)


def status_tr(s: str) -> str:
    return STATUS_TR.get(s, s)


@dataclass
class Source:
    kind: str                       # ais-anomaly | official | news | dsc | sdr | navtex
    detail: str = ""
    org: str | None = None
    url: str | None = None
    ts: str = field(default_factory=now_iso)

    def key(self) -> str:
        return f"{self.kind}|{self.org or ''}|{self.detail[:80]}"


@dataclass
class Vessel:
    name: str | None = None
    mmsi: int | None = None
    type: str | None = None
    callsign: str | None = None


@dataclass
class WeatherContext:
    wind_kn: float
    gust_kn: float
    wave_m: float | None
    wind_dir: int               # 0-360 degrees
    beaufort: int               # 0-12
    summary_tr: str
    summary_en: str
    station_name: str | None = None
    distance_nm: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> WeatherContext:
        return WeatherContext(**d)


@dataclass
class StraitStatus:
    id: str                     # "bosphorus" | "dardanelles"
    name: str                   # "İstanbul Boğazı" | "Çanakkale Boğazı"
    status: str                 # "open" | "caution" | "suspended"
    status_tr: str              # "Trafik Normal" | "Tedbirli Geçiş" | "Geçiş Askıya Alındı"
    reason: str | None = None   # "Yoğun Sis (Görüş < 300m)"
    active_vessels_in_transit: int = 0
    avg_speed_kn: float = 0.0
    last_update: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> StraitStatus:
        return StraitStatus(**d)


@dataclass
class MarineSafetyRating:
    area: str                   # "Marmara Denizi", "Saroz Körfezi", vb.
    score: int                  # 0 - 100
    status: str                 # "good" (>=75) | "caution" (45-74) | "danger" (<45)
    wave_m: float | None
    wind_kn: float
    gust_kn: float
    recommendation_tr: str
    recommendation_en: str
    last_update: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> MarineSafetyRating:
        return MarineSafetyRating(**d)


@dataclass
class CpaEvent:
    mmsi1: int
    mmsi2: int
    cpa_nm: float               # Closest Point of Approach in nautical miles (< 0.35 NM)
    tcpa_min: float             # Time to CPA in minutes (0 < TCPA <= 12 min)
    lat: float
    lon: float
    sog1_kn: float
    sog2_kn: float
    vessel1_name: str | None = None
    vessel2_name: str | None = None
    ts: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> CpaEvent:
        return CpaEvent(**d)


@dataclass
class Incident:
    id: str
    type: str = IncidentType.UNKNOWN.value
    status: str = Status.SIGNAL.value
    confidence: float = 0.2
    severity: str = Severity.INFO.value
    lat: float | None = None
    lon: float | None = None
    area: str = ""
    vessel: Vessel = field(default_factory=Vessel)
    casualties: int | None = None
    first_seen: str = field(default_factory=now_iso)
    last_update: str = field(default_factory=now_iso)
    sources: list[Source] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)   # coastal names extracted from text
    coarse: bool = False                             # position is a city centre, not a fix
    track: list[list[float]] = field(default_factory=list)  # [[lat, lon], ...] coordinates history
    heading: float | None = None
    vessel_type: str = "unknown"
    weather_context: WeatherContext | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Incident:
        d = dict(d)
        d.setdefault("id", "unknown")
        d.setdefault("track", [])
        d.setdefault("heading", None)
        d.setdefault("vessel_type", "unknown")
        d["vessel"] = Vessel(**(d.get("vessel") or {}))
        d["sources"] = [Source(**s) for s in d.get("sources", [])]
        wc = d.get("weather_context")
        if wc and isinstance(wc, dict):
            d["weather_context"] = WeatherContext.from_dict(wc)
        elif not isinstance(wc, WeatherContext):
            d["weather_context"] = None
        return Incident(**d)

    def add_source(self, s: Source) -> bool:
        """Append a source unless an equivalent one is already present."""
        if s.key() in {x.key() for x in self.sources}:
            return False
        self.sources.append(s)
        self.last_update = now_iso()
        return True


@dataclass
class Warning:
    id: str
    headline: str
    area: str = ""
    severity: str = Severity.MINOR.value
    kind: str = "marine-weather"    # marine-weather | metar | earthquake | gdacs | eonet | nav-warning | navtex
    onset: str | None = None
    expires: str | None = None
    org: str = ""
    url: str | None = None
    issued: str = field(default_factory=now_iso)
    last_update: str = field(default_factory=now_iso)
    raw: str = ""
    lat: float | None = None     # centroid / epicentre, for the map
    lon: float | None = None
    value: float | None = None   # magnitude or wave height, used to match duplicates
    sources: list[Source] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.sources and self.org:
            self.sources.append(Source(kind=self.kind, org=self.org,
                                       detail=self.headline[:200], url=self.url, ts=self.issued))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Warning:
        d = dict(d)
        d["sources"] = [Source(**s) for s in d.get("sources", [])]
        return Warning(**d)

    def add_source(self, s: Source) -> bool:
        if s.key() in {x.key() for x in self.sources}:
            return False
        self.sources.append(s)
        self.last_update = now_iso()
        return True

    @property
    def orgs(self) -> list[str]:
        seen, out = set(), []
        for s in self.sources:
            o = s.org or s.kind
            if o not in seen:
                seen.add(o)
                out.append(o)
        return out


def stable_hash(s: str, n: int = 5) -> str:
    """Python's built-in hash() is salted per process, so an id built from it
    changes on every CI run and the same story lands as a fresh record."""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def make_id(kind: str, lat: float | None, lon: float | None, ts: str | None = None) -> str:
    """Stable-ish id: same kind + rounded position + day -> same id (dedupes re-runs)."""
    ts = ts or now_iso()
    day = ts[:10]
    raw = f"{kind}:{round(lat or 0, 2)}:{round(lon or 0, 2)}:{day}"
    return f"{day}-{kind}-{hashlib.sha1(raw.encode()).hexdigest()[:6]}"
