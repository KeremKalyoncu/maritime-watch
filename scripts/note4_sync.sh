#!/data/data/com.termux/files/usr/bin/bash
# Sync maritime-watch on the Note 4 / Termux edge host and restart the bot.
# Usage: bash scripts/note4_sync.sh
set -euo pipefail
ROOT="${HOME}/maritime-watch"
cd "$ROOT"

echo "[note4] python=$(python --version 2>&1)"
echo "[note4] fetching origin/main…"
git fetch origin
git reset --hard origin/main

# Single getUpdates consumer
pkill -f "python run.py --bot" 2>/dev/null || true
sleep 2
tmux kill-session -t bot 2>/dev/null || true
sleep 1
tmux new-session -d -s bot -c "$ROOT" "python run.py --bot --send"
sleep 2
tmux capture-pane -t bot -p -S -8 || true
echo "[note4] bot session restarted"
