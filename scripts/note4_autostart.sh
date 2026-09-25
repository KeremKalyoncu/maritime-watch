#!/data/data/com.termux/files/usr/bin/bash
# Start whatever is missing on the Note 4 edge host, in the right order:
#   social  maritime-social --all (bot + scheduler + :8088 webhook listener)
#   engine  maritime-watch --loop (writes web/data locally, pushes alerts to :8088)
# Each runs under a respawn loop: an old phone's low-memory killer can take a
# process down (it did during a Pillow build), and nobody watches the screen.
# Safe to call repeatedly; ~/.bashrc calls it on every Termux start.
set -uo pipefail

main() {
  local social_dir="${HOME}/maritime-social"
  local engine_dir="${HOME}/maritime-watch"
  local webhook="${MARITIME_WEBHOOK_URL:-http://127.0.0.1:8088/webhook/alert}"
  local respawn='echo "[autostart] $(date +%H:%M:%S) exited ($?), restarting in 60s"; sleep 60'

  if [ -d "$social_dir" ] && ! tmux has-session -t social 2>/dev/null; then
    tmux new-session -d -s social -c "$social_dir" \
      "while :; do python run.py --all; $respawn; done"
    echo "[autostart] social started"
  fi

  if [ -d "$engine_dir" ] && ! tmux has-session -t engine 2>/dev/null; then
    # give the social webhook listener a head start
    tmux new-session -d -s engine -c "$engine_dir" \
      "sleep 15; while :; do python run.py --loop --alert-webhook $webhook; $respawn; done"
    echo "[autostart] engine started"
  fi
}

main "$@"
exit
