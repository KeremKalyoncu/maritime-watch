#!/usr/bin/env python3
"""Maritime Watch Core Engine Orchestrator.

Pure computation, scraping, marine physics, safety analysis and web dashboard generation.
Zero messaging dependencies. Emits data to web/data/*.json, web/feed.xml and optional
0-latency emergency webhooks.

Usage:
  python run.py --once                   run one cycle, write data, then exit
  python run.py --once --serve           run one cycle, then serve the web dashboard on :8000
  python run.py --loop                   cycle every loop.interval_seconds (default 900s)
  python run.py --serve                  just serve web/ (no cycle)
  python run.py --alert-webhook URL      push critical emergency events to external listener

flags: --no-ais  --no-scrape  --port N  --config PATH
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
import threading
import time
from pathlib import Path

# Windows ve non-UTF8 konsollarda emojili logların çökmesini engelle
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.config import load_config
from src.ingest import _net
from src.ingest.ais_stream import capture_ais
from src.ingest.eonet import fetch_eonet
from src.ingest.gdacs import fetch_gdacs
from src.ingest.metar import fetch_metar
from src.ingest.navwarn import fetch_navwarnings
from src.ingest.news import fetch_news
from src.ingest.official import gather_official
from src.ingest.openmeteo import (  # noqa: F401 — fetch_marine_warnings: tests / back-compat
    fetch_forecast_points,
    fetch_marine_warnings,
    warnings_from_forecast,
)
from src.ingest.openmeteo import reset_cache as reset_openmeteo_cache
from src.ingest.quakes import fetch_quakes
from src.ingest.reliefweb import fetch_reliefweb
from src.model import Incident, Source, Vessel, make_id
from src.process.anomaly import VesselState, detect
from src.process.classify import classify, enrich_weather_context
from src.process.cpa import cpa_events_to_incidents, detect_cpa_risks
from src.process.dedup import correlate
from src.process.prune import clear_passed_weather, prune
from src.process.safety_index import render_safety_index
from src.process.shiptype import hazard_category, is_large_vessel
from src.render.feed import build_feed
from src.render.health import write_health
from src.render.mapdata import enrich_incident_tracks, write_summary
from src.render.outlook import render_outlook
from src.render.stats import build_stats
from src.render.straits import render_straits_status
from src.render.weather_grid import render_weather_grid
from src.store import Store

_TYPE_FOR = {
    "nav-status": "drift",
    "speed-drop": "drift",
    "ais-gap": "distress",
    "course-spike": "unknown",
    "ais-sart": "distress",
    "rot-spike": "rot-spike",
    "grounding-risk": "grounding-risk",
}


def dispatch_emergency_webhook(
    webhook_url: str | None,
    token: str | None,
    payload: dict,
) -> None:
    """Optionally emit an emergency incident to maritime-social or external hub with 0 latency."""
    if not webhook_url:
        return
    try:
        import requests

        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Maritime-Token"] = token
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=4)
        if resp.status_code < 300:
            print(f"[webhook:emit] event={payload.get('event_id')} sent to {webhook_url}")
        else:
            print(f"[webhook:warn] status {resp.status_code} from {webhook_url}")
    except Exception as e:
        print(f"[webhook:error] {e}")


def cycle(
    cfg: dict,
    *,
    webhook_url: str | None = None,
    webhook_token: str | None = None,
    do_ais: bool = True,
    do_scrape: bool = True,
) -> None:
    started = time.time()
    root = Path(cfg["_root"])
    web_data = root / "web" / "data"
    store = Store(str(web_data), log_dir=str(root / "data"))
    src = cfg.get("sources", {})
    touched: set[str] = set()
    health: list[dict] = []

    # Config override for webhook url and token
    if not webhook_url:
        webhook_url = cfg.get("alert", {}).get("webhook_url") or None
    if not webhook_token:
        webhook_token = cfg.get("alert", {}).get("webhook_token") or None

    _net.SAMPLES_ALLOWED = bool(src.get("use_samples_when_down", False))
    _net.reset_status()
    reset_openmeteo_cache()

    def _safe(label, fn, default):
        try:
            r = fn()
            n = len(r) if isinstance(r, (list, tuple)) else None
            health.append({"source": label, "ok": True, "items": n, "error": None})
            return r
        except Exception as e:
            print(f"[{label}] error: {e}")
            health.append({"source": label, "ok": False, "items": None, "error": str(e)[:200]})
            return default

    if do_ais:
        records = capture_ais(cfg)
        positions = [r for r in records if r.get("msg_type") != "safety"]
        safety = [r for r in records if r.get("msg_type") == "safety"]
        print(f"[ais] {len(positions)} position(s), {len(safety)} safety msg(s)")

        vs = VesselState(str(root / "data" / "vessels.json"), cfg["ais"]["vessel_history"])
        seen_now = {str(p["mmsi"]) for p in positions if p.get("mmsi") is not None}
        vs.update(positions)
        anomalies = detect(vs, positions, cfg, seen_now)
        forgotten = vs.prune(cfg["ais"].get("vessel_ttl_hours", 12))
        vs.save()
        if forgotten:
            print(f"[ais] {forgotten} vessel(s) aged out of the track store")
        print(f"[anomaly] {len(anomalies)} flag(s)")
        for an in anomalies:
            kind = "ais-sart" if an.kind == "ais-sart" else "ais-anomaly"
            vstate = vs.data.get(str(an.mmsi), {})
            vessel_obj = Vessel(
                name=an.name or vstate.get("name") or None,
                mmsi=an.mmsi,
                type=str(vstate.get("type_code")) if vstate.get("type_code") is not None else None,
                callsign=vstate.get("callsign"),
                draught=vstate.get("draught"),
                length=vstate.get("length"),
                width=vstate.get("width"),
                destination=vstate.get("destination"),
                eta=vstate.get("eta"),
                cargo_hazard=hazard_category(vstate.get("type_code"), an.name),
                is_large_vessel=is_large_vessel(vstate.get("length")),
            )
            inc = Incident(
                id=make_id("ais", an.lat, an.lon),
                type=_TYPE_FOR.get(an.kind, "unknown"),
                lat=an.lat,
                lon=an.lon,
                vessel=vessel_obj,
            )
            inc.sources.append(Source(kind=kind, org="AIS", detail=f"{an.kind}: {an.detail}"))
            inc = correlate(store, inc)
            touched.add(store.upsert_incident(inc).id)

        cpa_events = detect_cpa_risks(positions)
        if cpa_events:
            print(f"[cpa] {len(cpa_events)} collision risk encounter(s) detected")
            for cpa_inc in cpa_events_to_incidents(cpa_events):
                cpa_inc = correlate(store, cpa_inc)
                touched.add(store.upsert_incident(cpa_inc).id)

        for s in safety:
            if not s.get("text"):
                continue
            inc = Incident(
                id=make_id("aissafe", s.get("lat"), s.get("lon")),
                type="distress",
                lat=s.get("lat"),
                lon=s.get("lon"),
                vessel=Vessel(mmsi=s.get("mmsi")),
            )
            inc.sources.append(
                Source(kind="ais-safety", org="AIS", detail=f"ch {s.get('channel')}: {s.get('text')}")
            )
            inc = correlate(store, inc)
            touched.add(store.upsert_incident(inc).id)

    forecast_pts = None
    wx_seen = set()
    extra_warns_ran = False

    def push_warning(w):
        if w:
            store.upsert_warning(w)
            if w.area:
                wx_seen.add(w.area)

    if do_scrape:
        if src.get("official", True):
            off_inc, off_warn = gather_official(cfg)
            for c in off_inc:
                c = correlate(store, c)
                touched.add(store.upsert_incident(c).id)
            for w in off_warn:
                push_warning(w)

        if src.get("news", True):
            news = _safe("news", lambda: fetch_news(cfg), [])
            print(f"[news] {len(news)} item(s)")
            for c in news:
                c = correlate(store, c)
                touched.add(store.upsert_incident(c).id)

        extra_warns = []
        if src.get("openmeteo", True):
            forecast_pts = _safe("openmeteo", lambda: fetch_forecast_points(cfg), []) or []
            extra_warns += warnings_from_forecast(cfg, forecast_pts)
            print(f"[openmeteo] forecast points={len(forecast_pts)}")
        if src.get("quakes", True):
            extra_warns += _safe("quakes", lambda: fetch_quakes(cfg), [])
        if src.get("navwarn", True):
            extra_warns += _safe("navwarn", lambda: fetch_navwarnings(cfg), [])
        if src.get("gdacs", True):
            extra_warns += _safe("gdacs", lambda: fetch_gdacs(cfg), [])
        if src.get("eonet", True):
            extra_warns += _safe("eonet", lambda: fetch_eonet(cfg), [])
        if src.get("reliefweb", True):
            extra_warns += _safe("reliefweb", lambda: fetch_reliefweb(cfg), [])
        if src.get("metar", True):
            extra_warns += _safe("metar", lambda: fetch_metar(cfg), [])
        extra_warns_ran = True
        print(f"[extra] {len(extra_warns)} warning(s)")
        for w in extra_warns:
            push_warning(w)

    for inc in store.active_incidents():
        classify(inc)
    for iid in touched:
        inc = store.incidents.get(iid)
        if inc:
            print(f"[engine:incident] {inc.id} status={inc.status} type={inc.type} sev={inc.severity}")
            if webhook_url and inc.severity in ("major", "critical"):
                desc = (
                    getattr(inc, "summary", "")
                    or (inc.notes[0] if getattr(inc, "notes", None) else "")
                    or (inc.sources[0].detail if getattr(inc, "sources", None) and inc.sources else "")
                )
                dispatch_emergency_webhook(
                    webhook_url,
                    webhook_token,
                    {
                        "event_id": inc.id,
                        "priority": inc.severity,
                        "category": inc.type,
                        "area": inc.area or "",
                        "lat": inc.lat,
                        "lon": inc.lon,
                        "title": getattr(inc, "type_tr", inc.type),
                        "description": desc,
                        "created_at": getattr(inc, "last_update", "") or getattr(inc, "first_seen", ""),
                    },
                )

    wx_live = do_scrape and all(_net.STATUS.get(k) != "sample" for k in _net.STATUS)
    for w in clear_passed_weather(store, wx_seen, wx_live and bool(wx_seen or extra_warns_ran)):
        print(f"[weather:passed] {w.area}: {getattr(w, 'headline', '')}")

    if forecast_pts is None:
        try:
            forecast_pts = fetch_forecast_points(cfg)
        except Exception as e:
            print(f"[forecast] fetch error: {e}")
            forecast_pts = None

    try:
        render_outlook(cfg, web_data / "outlook.json", points=forecast_pts)
    except Exception as e:
        print(f"[outlook:error] render error: {e}")

    dw, di = prune(store, cfg)
    if dw or di:
        print(f"[prune] {dw} warning(s) expired, {di} incident(s) closed/removed")

    fetch_status = dict(_net.STATUS)
    dead = sorted(k for k, v in fetch_status.items() if v != "live")
    if dead:
        print(f"[fetch] canli olmayan kaynak: {', '.join(dead)}")
    h = write_health(
        str(web_data),
        health,
        started,
        len(store.active_incidents()),
        len(store.active_warnings()),
        fetch_status=fetch_status,
    )
    down = sorted(set(h["sources_down"]) | {k for k, v in fetch_status.items() if v == "down"})
    if len(down) >= 3:
        print(f"[health:warn] {len(down)} kaynak yanıt vermiyor: {', '.join(down)}")
    print(f"[health] {h['sources_ok']}/{h['sources_total']} kaynak OK, {h['cycle_seconds']}s")

    try:
        enrich_incident_tracks(store, root / "data" / "vessels.json")
    except Exception as e:
        print(f"[tracks] enrich error: {e}")

    grid_payload = None
    try:
        grid_payload = render_weather_grid(cfg, web_data / "weather_overlay.json", points=forecast_pts)
        for inc in store.active_incidents():
            enrich_weather_context(inc, grid_payload.get("points", []))
    except Exception as e:
        print(f"[weather_grid] render error: {e}")

    try:
        vessels_file = root / "data" / "vessels.json"
        vessels_dict = {}
        if vessels_file.exists():
            try:
                vessels_dict = json.loads(vessels_file.read_text("utf-8") or "{}")
            except Exception:
                vessels_dict = {}
        render_straits_status(store, web_data / "straits.json", vessels_data=vessels_dict)
    except Exception as e:
        print(f"[straits] render error: {e}")

    try:
        pts = grid_payload.get("points", []) if grid_payload else []
        storm_areas = {w.area for w in store.active_warnings() if w.area}
        render_safety_index(pts, storm_areas=storm_areas, out_file=web_data / "safety_index.json")
    except Exception as e:
        print(f"[safety_index] render error: {e}")

    store.trim_events()
    store.save()
    build_feed(store, str(web_data))
    write_summary(store, str(web_data), stale_hours=cfg.get("alert", {}).get("stale_hours", 2))
    build_stats(str(root / "data" / "events.jsonl"), str(web_data))
    print(f"[done] incidents={len(store.active_incidents())} warnings={len(store.active_warnings())}")


def serve(cfg: dict, port: int = 8000) -> None:
    web = Path(cfg["_root"]) / "web"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web))
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"[serve] http://127.0.0.1:{port}  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Maritime Watch: Turkiye deniz analiz ve izleme motoru")
    ap.add_argument("--once", action="store_true", help="run one cycle then exit")
    ap.add_argument("--loop", action="store_true", help="run cycles forever")
    ap.add_argument("--serve", action="store_true", help="serve web/ on localhost")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--alert-webhook", default=None, help="HTTP URL to push critical emergency incidents")
    ap.add_argument("--alert-token", default=None, help="Auth token for emergency webhook")
    ap.add_argument("--no-ais", action="store_true")
    ap.add_argument("--no-scrape", action="store_true")
    ap.add_argument("--send", action="store_true", help="Deprecated: Telegram alerts moved to maritime-social")
    ap.add_argument("--bot", action="store_true", help="Deprecated: Telegram bot moved to maritime-social")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    if args.send or args.bot:
        print("[compat] Note: --send / --bot flags are deprecated; messaging moved to maritime-social.")

    cfg = load_config(args.config)
    webhook_url = args.alert_webhook or cfg.get("alert", {}).get("webhook_url", "")
    webhook_token = args.alert_token or cfg.get("alert", {}).get("webhook_token", "")

    if args.serve and not (args.once or args.loop):
        serve(cfg, args.port)
        return
    if args.serve:
        threading.Thread(target=serve, args=(cfg, args.port), daemon=True).start()

    if args.loop:
        interval = cfg["loop"]["interval_seconds"]
        while True:
            try:
                cycle(
                    cfg,
                    webhook_url=webhook_url,
                    webhook_token=webhook_token,
                    do_ais=not args.no_ais,
                    do_scrape=not args.no_scrape,
                )
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[cycle] error: {e}")
            print(f"[loop] sleeping {interval}s\n")
            time.sleep(interval)
    else:
        cycle(
            cfg,
            webhook_url=webhook_url,
            webhook_token=webhook_token,
            do_ais=not args.no_ais,
            do_scrape=not args.no_scrape,
        )
        if args.serve:
            while True:
                time.sleep(3600)


if __name__ == "__main__":
    main()
