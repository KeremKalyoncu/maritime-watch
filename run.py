#!/usr/bin/env python3
"""Maritime Watch orchestrator.

  py run.py --once            one cycle (dry-run alerts), then exit
  py run.py --once --serve    one cycle, then serve the map on :8000
  py run.py --loop            cycle every loop.interval_seconds
  py run.py --serve           just serve web/ (no cycle)
  py run.py --once --send     actually send Telegram alerts (needs .env)

  flags: --no-ais  --no-scrape  --port N  --config PATH
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import threading
import time
from pathlib import Path

from src.alert.telegram import Notifier
from src.config import load_config
from src.ingest.ais_stream import capture_ais
from src.ingest.official import gather_official
from src.model import Incident, Source, Vessel, make_id
from src.process.anomaly import VesselState, detect
from src.process.classify import classify
from src.process.dedup import correlate
from src.render.feed import build_feed
from src.render.mapdata import write_summary
from src.store import Store

_TYPE_FOR = {
    "nav-status": "drift",
    "speed-drop": "drift",
    "ais-gap": "distress",
    "course-spike": "unknown",
}


def cycle(cfg: dict, *, dry: bool = True, do_ais: bool = True, do_scrape: bool = True) -> None:
    root = Path(cfg["_root"])
    web_data = root / "web" / "data"
    store = Store(str(web_data), log_dir=str(root / "data"))
    notifier = Notifier(cfg)

    if do_ais:
        positions = capture_ais(cfg)
        print(f"[ais] {len(positions)} position(s)")
        vs = VesselState(str(root / "data" / "vessels.json"), cfg["ais"]["vessel_history"])
        seen_now = {str(p["mmsi"]) for p in positions if p.get("mmsi") is not None}
        vs.update(positions)
        anomalies = detect(vs, positions, cfg, seen_now)
        vs.save()
        print(f"[anomaly] {len(anomalies)} flag(s)")
        for an in anomalies:
            inc = Incident(
                id=make_id("ais", an.lat, an.lon),
                type=_TYPE_FOR.get(an.kind, "unknown"),
                lat=an.lat, lon=an.lon,
                vessel=Vessel(name=an.name or None, mmsi=an.mmsi),
            )
            inc.sources.append(Source(kind="ais-anomaly", org="AIS", detail=f"{an.kind}: {an.detail}"))
            inc = correlate(store, inc)
            classify(inc)
            store.upsert_incident(inc)

    if do_scrape:
        incs, warns = gather_official(cfg)
        print(f"[scrape] {len(incs)} report(s), {len(warns)} warning(s)")
        for c in incs:
            c = correlate(store, c)
            classify(c)
            saved = store.upsert_incident(c)
            notifier.incident(saved, dry=dry)
        for w in warns:
            if store.upsert_warning(w):
                notifier.warning(w, dry=dry)

    # source merges may have bumped a signal up to confirmed
    for inc in store.active_incidents():
        classify(inc)

    store.save()
    build_feed(store, str(web_data))
    write_summary(store, str(web_data))
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
    ap = argparse.ArgumentParser(description="Maritime Watch: Turkiye deniz olayi izleme")
    ap.add_argument("--once", action="store_true", help="run one cycle then exit")
    ap.add_argument("--loop", action="store_true", help="run cycles forever")
    ap.add_argument("--serve", action="store_true", help="serve web/ on localhost")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--send", action="store_true", help="really send Telegram (default: dry-run)")
    ap.add_argument("--no-ais", action="store_true")
    ap.add_argument("--no-scrape", action="store_true")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    dry = not args.send

    if args.serve and not (args.once or args.loop):
        serve(cfg, args.port)
        return
    if args.serve:
        threading.Thread(target=serve, args=(cfg, args.port), daemon=True).start()

    if args.loop:
        interval = cfg["loop"]["interval_seconds"]
        while True:
            try:
                cycle(cfg, dry=dry, do_ais=not args.no_ais, do_scrape=not args.no_scrape)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[cycle] error: {e}")
            print(f"[loop] sleeping {interval}s\n")
            time.sleep(interval)
    else:
        cycle(cfg, dry=dry, do_ais=not args.no_ais, do_scrape=not args.no_scrape)
        if args.serve:
            while True:
                time.sleep(3600)


if __name__ == "__main__":
    main()
