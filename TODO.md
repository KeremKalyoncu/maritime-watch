# TODO / Roadmap

## Done

**Core**
- [x] Config (`config.yaml` + `.env`), CAP-like `Incident`/`Warning` model, JSON store + `events.jsonl`
- [x] AIS burst ingest (no hardware): PositionReport, ShipStaticData, SafetyBroadcast (msg 14)
- [x] AIS-SART / MOB (MMSI 970/972/974) → instant critical alert
- [x] Rule-based anomaly: nav-status, speed-drop, course-spike, ais-gap; persistent tracks
- [x] Ship-type-aware thresholds (fishing loiter suppressed, cargo/tanker sensitive)
- [x] Turkish text extraction: vessel name, coordinates (DMS + decimal), casualties, places
- [x] Incident entity resolution — merge by MMSI / vessel name / place / proximity + time window
- [x] Warning `same_hazard` merge — "N bağımsız kaynak doğruluyor"; same-source re-fetch is a refresh, not a confirmation
- [x] Classify: status ladder, confidence, severity, nearest port
- [x] Polygon sea areas (`regions.geojson`, point-in-polygon), no GIS dependency
- [x] Prune: TTL expiry, official "resolved" phrase closes an incident, seed drop once live

**Sources** (all `_safe`-wrapped)
- [x] Open-Meteo marine+wind, AFAD+USGS+EMSC quakes, Sahil Güvenlik, news RSS ×10,
      GDACS RSS, NASA EONET, coastal METAR; NGA NAVAREA III + ReliefWeb (code ready, endpoints down)

**Output**
- [x] Leaflet + OpenSeaMap map: region filter, TR/EN toggle, `#id` deep-link, stale-data banner, health line
- [x] `stats.html` + `stats.json` (by month / area / type / status, top vessels, resolution time)
- [x] `feed.xml` RSS, `summary.json`, `health.json`
- [x] Telegram: plain-Turkish messages, per-cycle digest (SART instant), `sendLocation`, operator health alert

**Quality**
- [x] Tests (69, offline) + eval harness (`eval/run_eval.py` → `REPORT.md`)
- [x] CI: ruff + pytest matrix (3.11/3.12/3.13) + eval, free GitHub Actions/Pages deploy
- [x] `ARCHITECTURE.md`, README, NOTICE, CONTRIBUTING

## Your part

- [ ] `git push`; add repo Secrets: `AISSTREAM_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- [ ] Settings → Pages → GitHub Actions; run `update-and-publish` once
- [ ] Telegram: add the bot as channel admin, set `TELEGRAM_CHAT_ID=@channel`
- [ ] (recommended) move off GitHub cron to a €1–4/mo VPS + `--loop` for real-time
- [ ] Reach out: newsroom data desk / balıkçı kooperatifi / AFAD-SG digital team

## Next

- [ ] Working NGA NAVAREA III endpoint, ReliefWeb v2, an MGM marine endpoint
- [ ] Kandilli (KOERI) as a fourth quake source
- [ ] Wire the DSC module (`data/dsc_alerts.jsonl` reader) when hardware / a KiwiSDR feed exists
- [ ] Route deviation vs a learned traffic model (currently only rule-based)
- [ ] Per-region Telegram channels (`/abone <bölge>`)
- [ ] Draw `regions.geojson` on the map; per-incident detail page with the AIS track
- [ ] Grow `eval/labels.json` with real historical cases; calibrate confidence weights
