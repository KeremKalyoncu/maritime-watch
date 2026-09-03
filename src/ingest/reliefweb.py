"""Active disasters for Turkey from the ReliefWeb API (free, no key).

Country-level only (no coordinates), so it feeds the map's timeline rather than a
pin. Useful as a slow, authoritative cross-check on the faster feeds.
"""

from __future__ import annotations

from ..model import Warning, now_iso
from ._net import get_json

# minimal query; we filter for Turkey on the name client-side
API = ("https://api.reliefweb.int/v1/disasters?appname=maritime-watch"
       "&limit=25&profile=list&sort[]=date.created:desc")
_TR = ("turkiye", "türkiye", "turkey")


def fetch_reliefweb(cfg: dict) -> list[Warning]:
    data, _live = get_json(API, "reliefweb.json")
    out: list[Warning] = []
    for row in (data or {}).get("data", []):
        f = row.get("fields") or {}
        name = f.get("name")
        if not name or not any(t in name.lower() for t in _TR):
            continue
        if (f.get("status") or "current") not in ("current", "alert", "ongoing"):
            continue
        created = (f.get("date") or {}).get("created") or now_iso()
        out.append(Warning(
            id=f"rw-{row.get('id') or abs(hash(name)) % 100000}",
            headline=f"ReliefWeb: {name[:220]}",
            area=cfg["region"]["name"],
            kind="gdacs",
            severity="minor",
            org="ReliefWeb",
            url=(row.get("href") or "https://reliefweb.int/"),
            issued=created,
        ))
    return out[:10]
