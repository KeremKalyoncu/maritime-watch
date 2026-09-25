#!/data/data/com.termux/files/usr/bin/bash
# Sync maritime-watch on the Note 4 / Termux edge host and (re)start the engine loop.
# The engine writes web/data/*.json locally, so maritime-social on the same phone
# reads fresh data from disk and gets critical incidents on its :8088 webhook at once.
# Usage: bash scripts/note4_sync.sh      (start maritime-social first: its listener must be up)
set -euo pipefail

# Everything lives in main(): bash reads a script lazily, and the git reset below
# rewrites this very file mid-run. Parsing the whole function first means the old
# and new versions never get spliced together.
main() {
  ROOT="${HOME}/maritime-watch"
  SOCIAL_ENV="${HOME}/maritime-social/.env"
  WEBHOOK_URL="${MARITIME_WEBHOOK_URL:-http://127.0.0.1:8088/webhook/alert}"
  cd "$ROOT"

  echo "[note4] python=$(python --version 2>&1)"

  # Must match maritime-social's INTERNAL_WEBHOOK_TOKEN, or its listener answers 401.
  TOKEN="${INTERNAL_WEBHOOK_TOKEN:-}"
  if [ -z "$TOKEN" ] && [ -f "$SOCIAL_ENV" ]; then
    TOKEN="$(grep -E '^INTERNAL_WEBHOOK_TOKEN=' "$SOCIAL_ENV" | tail -n1 | cut -d= -f2- | tr -d '"'"'"' \r')"
  fi

  # Stop the old engine first so it does not write state while we sync.
  tmux kill-session -t engine 2>/dev/null || true
  tmux kill-session -t bot 2>/dev/null || true          # pre-split "run.py --bot --send" session
  pkill -f "python run.py --loop" 2>/dev/null || true
  sleep 1

  # Track store and incident state live in data/ and web/data/; a hard reset would
  # roll them back to the last committed seed and wipe AIS history every sync.
  STATE="${TMPDIR:-/tmp}/maritime-watch-state.tar"
  tar -cf "$STATE" data web/data
  echo "[note4] fetching origin/main…"
  git fetch origin
  git reset --hard origin/main
  tar -xf "$STATE"
  rm -f "$STATE"

  python -m pip install -q -r requirements.txt

  # Hand the token over through .env, never on the command line: argv shows up in ps.
  if [ -n "$TOKEN" ]; then
    touch .env
    if grep -q '^INTERNAL_WEBHOOK_TOKEN=' .env; then
      sed -i "s|^INTERNAL_WEBHOOK_TOKEN=.*|INTERNAL_WEBHOOK_TOKEN=$TOKEN|" .env
    else
      printf '\nINTERNAL_WEBHOOK_TOKEN=%s\n' "$TOKEN" >> .env
    fi
    chmod 600 .env
  fi

  # Same launcher ~/.bashrc uses: respawn loop, and starts social too if it is down.
  MARITIME_WEBHOOK_URL="$WEBHOOK_URL" bash "$ROOT/scripts/note4_autostart.sh"
  echo "[note4] engine loop started in tmux session 'engine' (webhook -> $WEBHOOK_URL)"
}

main "$@"
exit
