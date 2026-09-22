"""RFC 7946 Standard GeoJSON Exporter for Maritime Incidents and Vessel Telemetry.
Allows research institutions, GIS analysts, universities, and open data portals
to consume Turkish territorial waters maritime data in standard QGIS / ArcGIS format.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.model import STATUS_TR, TYPE_TR


def build_incidents_geojson(store) -> dict[str, Any]:
    """Export active incidents as an RFC 7946 FeatureCollection."""
    features = []

    for inc in store.active_incidents():
        if inc.lat is None or inc.lon is None:
            continue

        props: dict[str, Any] = {
            "id": inc.id,
            "type": inc.type,
            "type_tr": TYPE_TR.get(inc.type, inc.type),
            "status": inc.status,
            "status_tr": STATUS_TR.get(inc.status, inc.status),
            "severity": inc.severity,
            "confidence": inc.confidence,
            "area": inc.area,
            "first_seen": inc.first_seen,
            "last_update": inc.last_update,
            "vessel_name": inc.vessel.name if inc.vessel else None,
            "vessel_mmsi": inc.vessel.mmsi if inc.vessel else None,
            "vessel_type": inc.vessel_type,
            "heading": inc.heading,
            "casualties": inc.casualties,
            "has_track": bool(inc.track and len(inc.track) > 1),
            "sources_count": len(inc.sources),
        }

        if inc.weather_context:
            props["weather"] = {
                "wind_kn": inc.weather_context.wind_kn,
                "gust_kn": inc.weather_context.gust_kn,
                "wave_m": inc.weather_context.wave_m,
                "beaufort": inc.weather_context.beaufort,
                "summary": inc.weather_context.summary_tr,
            }

        if getattr(inc, "sar_drift", None):
            props["sar_drift"] = inc.sar_drift

        # RFC 7946: coordinates are [longitude, latitude]
        feature = {
            "type": "Feature",
            "id": inc.id,
            "geometry": {
                "type": "Point",
                "coordinates": [round(float(inc.lon), 5), round(float(inc.lat), 5)],
            },
            "properties": props,
        }
        features.append(feature)

        # If incident has a historical track, also emit a LineString feature
        if inc.track and len(inc.track) >= 2:
            track_coords = []
            for pt in inc.track:
                if len(pt) >= 2 and pt[0] is not None and pt[1] is not None:
                    # In inc.track, coordinates are stored as [lat, lon], so invert to [lon, lat]
                    track_coords.append([round(float(pt[1]), 5), round(float(pt[0]), 5)])
            if len(track_coords) >= 2:
                track_feature = {
                    "type": "Feature",
                    "id": f"{inc.id}-track",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": track_coords,
                    },
                    "properties": {
                        "parent_incident_id": inc.id,
                        "type": "incident_track",
                        "vessel_name": props.get("vessel_name"),
                    },
                }
                features.append(track_feature)

    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }


def build_vessels_geojson(vessels_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Export live vessels from state as an RFC 7946 FeatureCollection."""
    features = []
    if not vessels_data or not isinstance(vessels_data, dict):
        return {"type": "FeatureCollection", "features": []}

    from src.process.shiptype import category as ship_category

    for mmsi_str, v in vessels_data.items():
        if not isinstance(v, dict):
            continue
        track = v.get("track", [])
        if not track:
            continue
        last_pt = track[-1]
        lat, lon = last_pt.get("lat"), last_pt.get("lon")
        if lat is None or lon is None:
            continue

        try:
            mmsi_val = int(mmsi_str)
        except ValueError:
            mmsi_val = 0

        type_code = v.get("type_code")
        cat = ship_category(type_code) if type_code is not None else "other"

        props = {
            "mmsi": mmsi_val,
            "name": v.get("name") or "",
            "type_code": type_code,
            "category": cat,
            "sog": last_pt.get("sog"),
            "cog": last_pt.get("cog"),
            "nav_status": last_pt.get("nav"),
            "rot": last_pt.get("rot"),
            "draught": v.get("draught"),
            "length": v.get("length"),
            "width": v.get("width"),
            "destination": v.get("destination"),
            "eta": v.get("eta"),
            "last_seen": v.get("last_seen"),
        }

        # RFC 7946: [lon, lat]
        feature = {
            "type": "Feature",
            "id": f"mmsi-{mmsi_str}",
            "geometry": {
                "type": "Point",
                "coordinates": [round(float(lon), 5), round(float(lat), 5)],
            },
            "properties": props,
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }


def build_geojson(store, out_dir: str, vessels_data: dict[str, Any] | None = None) -> None:
    """Render incidents.geojson and vessels.geojson into target web/data directory."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    inc_gj = build_incidents_geojson(store)
    (out / "incidents.geojson").write_text(
        json.dumps(inc_gj, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ves_gj = build_vessels_geojson(vessels_data)
    (out / "vessels.geojson").write_text(
        json.dumps(ves_gj, ensure_ascii=False, indent=2), encoding="utf-8"
    )
