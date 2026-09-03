"""Data model. Two record types, Incident and Warning, loosely modelled on CAP.
Each keeps its list of sources plus a status/confidence used to flag unverified
items on the map."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

ISO = "%Y-%m-%dT%H:%M:%SZ"


def now_iso() -> str:
    return time.strftime(ISO, time.gmtime())


class IncidentType(str, Enum):
    GROUNDING = "grounding"
    COLLISION = "collision"
    DRIFT = "drift"
    DISTRESS = "distress"
    CAPSIZE = "capsize"
    FIRE = "fire"
    SINKING = "sinking"
    MOB = "man-overboard"
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


@dataclass
class Source:
    kind: str                       # ais-anomaly | official | news | dsc | sdr | navtex
    detail: str = ""
    org: Optional[str] = None
    url: Optional[str] = None
    ts: str = field(default_factory=now_iso)

    def key(self) -> str:
        return f"{self.kind}|{self.org or ''}|{self.detail[:80]}"


@dataclass
class Vessel:
    name: Optional[str] = None
    mmsi: Optional[int] = None
    type: Optional[str] = None
    callsign: Optional[str] = None


@dataclass
class Incident:
    id: str
    type: str = IncidentType.UNKNOWN.value
    status: str = Status.SIGNAL.value
    confidence: float = 0.2
    severity: str = Severity.INFO.value
    lat: Optional[float] = None
    lon: Optional[float] = None
    area: str = ""
    vessel: Vessel = field(default_factory=Vessel)
    casualties: Optional[int] = None
    first_seen: str = field(default_factory=now_iso)
    last_update: str = field(default_factory=now_iso)
    sources: list[Source] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Incident":
        d = dict(d)
        d["vessel"] = Vessel(**(d.get("vessel") or {}))
        d["sources"] = [Source(**s) for s in d.get("sources", [])]
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
    kind: str = "marine-weather"    # marine-weather | navtex | nav-warning
    onset: Optional[str] = None
    expires: Optional[str] = None
    org: str = ""
    url: Optional[str] = None
    issued: str = field(default_factory=now_iso)
    raw: str = ""
    lat: Optional[float] = None     # area centroid, for the map
    lon: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Warning":
        return Warning(**d)


def make_id(kind: str, lat: Optional[float], lon: Optional[float], ts: Optional[str] = None) -> str:
    """Stable-ish id: same kind + rounded position + day -> same id (dedupes re-runs)."""
    ts = ts or now_iso()
    day = ts[:10]
    raw = f"{kind}:{round(lat or 0, 2)}:{round(lon or 0, 2)}:{day}"
    return f"{day}-{kind}-{hashlib.sha1(raw.encode()).hexdigest()[:6]}"
