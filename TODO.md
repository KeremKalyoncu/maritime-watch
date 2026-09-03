# TODO / Roadmap

## Done (v1.0)

- [x] Repo skeleton, config (`config.yaml` + `.env`), CAP-like `Incident`/`Warning` model
- [x] JSON store + append-only event log
- [x] AIS ingest — aisstream.io burst capture, sample fallback, no hardware
- [x] Rule-based AIS anomaly: nav-status, speed-drop, course-spike, ais-gap; persistent vessel tracks
- [x] Correlation/dedup by position + time window
- [x] Classify: status ladder, confidence, severity, Turkish sea-area geocoding + place hints
- [x] Official scrapers: MGM marine warnings, Sahil Güvenlik, AFAD — defensive + cached samples
- [x] Telegram output: dry-run default, real send with `--send`, repeat-suppression
- [x] Leaflet + OpenSeaMap map, timeline, "doğrulanmadı" labels, auto-refresh
- [x] RSS feed (`feed.xml`) + `summary.json`
- [x] `src/sdr/` integration guide (DSC / NAVTEX / Whisper) + experimental stub
- [x] Tests (33, offline) + `.github/workflows/tests.yml`
- [x] `.github/workflows/update.yml` — free GitHub Actions + Pages deployment
- [x] README with legal-design section, NOTICE, CONTRIBUTING

## Your part (see README "Hızlı başlangıç")

- [ ] `git push` to GitHub
- [ ] AISSTREAM_KEY (free) → `.env` and repo Secrets
- [ ] Telegram bot token + chat id (free) → `.env` and repo Secrets
- [ ] Enable GitHub Pages (Settings → Pages → GitHub Actions) **or** pick a host
- [ ] Smoke test: `py run.py --once --serve`, open the map, send a dry-run alert
- [ ] Reach out: Sahil Güvenlik basın / AFAD / a newsroom data desk, a balıkçı kooperatifi

## Next

- [ ] `data/dsc_alerts.jsonl` reader → wire the DSC module into `run.py`
- [ ] NAVAREA III / Kıyı Emniyeti NAVTEX **text** feed (no radio) as `Warning(kind="navtex")`
- [ ] Polygon sea areas (GeoJSON) instead of bounding boxes
- [ ] Resolve/false-positive automation (match a later "kurtarıldı/sonuçlandı" official item to an open incident)
- [ ] Per-region Telegram channels so a balıkçı only gets their sea
- [ ] Map UI i18n (EN)
- [ ] AIS anomaly eval harness + a labelled synthetic set; publish precision/recall

## Later / maybe

- [ ] Optional AIS via local `AIS-catcher` / `rtl_ais` when hardware is present
- [ ] Whisper eval corpus + WER numbers in WRITEUP (only if the voice path proves worth it)
- [ ] Historical archive view (play back `events.jsonl`)
