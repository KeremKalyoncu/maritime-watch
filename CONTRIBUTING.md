# Contributing

Thanks for helping with coastal safety tooling. Keep changes small, honest, and
reviewable — especially anything that affects go/no-go windows or scores.

## Dev setup

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest -q
python eval/run_eval.py   # optional but nice
```

Python **3.11+** matches CI. The edge Telegram host should use the same major
line when possible (see README Termux notes).

## Before you open a PR

1. Prefer an **issue** first for behaviour changes (bug / feature templates).
2. Run `ruff check` and `pytest` locally; the `ci` workflow must stay green.
3. Do not commit `.env`, tokens, or `data/subscribers.json`.
4. Do not force-add gitignored publish artifacts unless you are the scheduled
   data cycle (Actions bot).

## Rules of the road

- **Nothing that receives, records, or redistributes private radio traffic.**
  Public output is official + open data only. See README “Hukuki tasarım” and
  `src/sdr/README.md`. PRs that break this will be closed.
- **Saying nothing beats saying something false.** Missing marine fields must
  not become calm/`ok`/`85/100`. Prefer `unknown` or an explicit “veri yok”.
- Scrapers must degrade safely: network/parse failure logs and returns empty,
  never raises out of `gather_official()`. Add a cached sample under
  `src/ingest/samples/` for offline tests **and** keep production
  `SAMPLES_ALLOWED=false` (see `tests/test_no_fixture_leak.py`).
- Anomaly rules stay explainable (no black-box ML on the core path). New rules
  need a test in `tests/test_anomaly.py` with a synthetic track.
- Keep runtime deps minimal. Prefer the standard library.
- Security-sensitive reports → [`SECURITY.md`](SECURITY.md), not a public issue.

## Good first issues

- New official source (coastal Valilik, Kıyı Emniyeti NAVTEX text feed).
- Clearer empty/stale copy on the web Bugün panel or bot.
- Docs / i18n of the map UI.
- Eval corpus growth (`eval/`) with labelled coastal cases.

## Out of scope (for now)

New database, React rewrite, continuous AIS on the phone, SDR/DSC revival as a
product bet, inventing windows when Open-Meteo is down.
