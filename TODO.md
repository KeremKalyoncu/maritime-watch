# TODO / Roadmap

## Done

- [x] Repo skeleton, config (`config.yaml` + `.env`), CAP-like `Incident`/`Warning` model
- [x] JSON store + append-only event log
- [x] AIS ingest: aisstream.io burst capture, sample fallback, no hardware
- [x] AIS-SART / MOB (MMSI 970/972/974) + AIS safety broadcast (msg 14)
- [x] Rule-based AIS anomaly: nav-status, speed-drop, course-spike, ais-gap; persistent tracks
- [x] Correlation/dedup by position + time window
- [x] Classify: status ladder, confidence, severity, Turkish sea-area geocoding + place hints
- [x] Sources: Open-Meteo marine+wind, AFAD earthquakes, Sahil Güvenlik, news RSS (5 feeds),
      GDACS RSS, coastal METAR; NGA NAVAREA III (code ready, endpoint down)
- [x] Rich Telegram messages: coordinates, nearest port + bearing, Google Maps link,
      map deep-link, MarineTraffic link, `sendLocation` pin; sends confirmed + probable + SART
- [x] Leaflet + OpenSeaMap map, timeline, `#id` deep-link, "doğrulanmadı" labels, auto-refresh
- [x] RSS feed (`feed.xml`) + `summary.json`
- [x] `src/sdr/` integration guide (DSC / NAVTEX / Whisper) + experimental stub
- [x] Tests (48, offline) + `.github/workflows/tests.yml`
- [x] `.github/workflows/update.yml`: free GitHub Actions + Pages deployment
- [x] README with data-source table + legal-design section, NOTICE, CONTRIBUTING

## Your part (see README "Hızlı başlangıç")

- [ ] `git push` to GitHub
- [ ] AISSTREAM_KEY (free) → `.env` and repo Secrets
- [ ] Telegram bot token + chat id (free) → `.env` and repo Secrets
- [ ] Enable GitHub Pages (Settings → Pages → GitHub Actions) **or** pick a host
- [ ] Smoke test: `py run.py --once --serve`, open the map, send a dry-run alert
- [ ] Reach out: Sahil Güvenlik basın / AFAD / a newsroom data desk, a balıkçı kooperatifi

## Next

- [ ] Working NGA NAVAREA III endpoint (current one 404s) or Kıyı Emniyeti NAVTEX text feed
- [ ] MGM marine endpoint if a stable one turns up
- [ ] `data/dsc_alerts.jsonl` reader → wire the DSC module into `run.py`
- [ ] Polygon sea areas (GeoJSON) instead of bounding boxes
- [ ] Resolve/false-positive automation (match a later "kurtarıldı/sonuçlandı" item to an open incident)
- [ ] Per-region Telegram channels so a balıkçı only gets their sea
- [ ] Map UI i18n (EN)
- [ ] AIS anomaly eval harness + a labelled synthetic set; publish precision/recall

## Later / maybe

- [ ] Optional AIS via local `AIS-catcher` / `rtl_ais` when hardware is present
- [ ] Whisper eval corpus + WER numbers in WRITEUP (only if the voice path proves worth it)
- [ ] Historical archive view (play back `events.jsonl`)
