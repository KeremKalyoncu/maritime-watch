# Contributing

## Dev setup

```bash
py -m pip install -r requirements-dev.txt
py -m pytest
```

## Rules of the road

- **Nothing that receives, records, or redistributes private radio traffic.** The
  public output is official + open data only. See README "Hukuki tasarım" and
  `src/sdr/README.md`. PRs that break this will be closed.
- Scrapers must degrade safely: any network/parse failure logs and returns empty,
  never raises out of `gather_official()`. Add a cached sample under
  `src/ingest/samples/` for every new source and a test in
  `tests/test_scrapers_offline.py`.
- Anomaly rules stay explainable (no black-box ML in the core path). New rules
  need a test in `tests/test_anomaly.py` with a synthetic track.
- Keep runtime deps minimal (currently 5). Prefer the standard library.

## Good first issues

- New official source (a coastal Valilik, Kıyı Emniyeti NAVTEX text feed).
- Better geocoding (polygon sea areas instead of bounding boxes).
- `data/dsc_alerts.jsonl` reader wiring the DSC module into `run.py`.
- i18n of the map UI (currently Turkish only).
