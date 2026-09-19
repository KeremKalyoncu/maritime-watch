# Security Policy

Maritime Watch publishes **safety-adjacent** forecasts and alerts. Wrong data can be worse than no data. Please treat integrity bugs as security-relevant.

## Supported versions

| Surface | Supported |
|---------|-----------|
| `main` branch (GitHub Pages + Actions cycle) | Yes |
| Telegram bot on a self-hosted edge node (e.g. Termux) | Yes, if tracking `main` |
| Forks / old tags | Best-effort only |

## What to report privately

Please **do not** open a public issue for:

- Leaked or exposed secrets (Telegram bot token, AISStream key, any API credential)
- Ability to publish **fixture/sample** weather or incidents as if they were live
- Paths that invent a green / “safe” score when measurements are missing
- Subscriber `chat_id` or other personal data appearing in the public repo, Pages artifact, or commit history
- RCE / dependency supply-chain issues in this repository

Use GitHub **Security → Advisories → Report a vulnerability** (preferred), or email the maintainer listed on the GitHub profile if advisories are unavailable.

Include: affected commit/SHA or Pages timestamp, steps to reproduce, and whether anything was already exposed publicly.

## What can stay public

- UI bugs, map/panel layout issues
- Missing sea areas in `outlook.json` when clearly a data/coverage problem
- Documentation gaps, Dependabot bumps, CI failures
- Feature ideas (use the feature issue template)

## Maintainer commitments

- Rotate any confirmed leaked token immediately and purge it from git history when needed
- Prefer silence or an explicit “veri yok / ölçüm eksik” over a fabricated calm forecast
- `data/subscribers.json` and `.env` stay gitignored; they must never be force-added to Pages
- Production ingest must not publish `sample`-backed Open-Meteo / scraper fixtures (`tests/test_no_fixture_leak.py`)

## Secrets checklist (operators)

```text
AISSTREAM_KEY          # aisstream.io — never commit
TELEGRAM_BOT_TOKEN     # BotFather — never commit
TELEGRAM_CHAT_ID       # channel/group id — never commit
data/subscribers.json  # chat ids — host only
```

Copy from `.env.example` locally. GitHub Actions secrets are set in the repo settings for the scheduled cycle only.

## Out of scope

Private radio / voice interception, recording, or redistribution (see README *Hukuki tasarım* and `src/sdr/README.md`). PRs that add this will be rejected.
