"""Ask GitHub to rebuild the public map now, from the phone's --loop (KARARLAR K26).

GitHub runs the `update.yml` cron 2-7 hours late (39 runs, 24.09-02.10), so the map
showed its "data is old" banner (alert.stale_hours = 2) most of the day. A
workflow_dispatch is not queued behind the cron backlog. At most one per
`every_minutes`; the run itself is a normal `run.py --once` on GitHub.

Token: GITHUB_DISPATCH_TOKEN in .env, a fine-grained PAT for this repository only
with "Actions: write". GitHub lists POST .../actions/workflows/{id}/dispatches under
that permission; it cannot change code (repository_dispatch would need "Contents:
write", so it is not used). The token is a secret: never printed, never an argument.

Only --loop builds this (run.py); `--once` on GitHub never dispatches, so a run can
not trigger the next one.
"""

from __future__ import annotations

import os
import time

API = "https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
REFUSED_BACKOFF_S = 6 * 3600  # 401/403/404/422: token or settings wrong; do not hammer GitHub


class PagesDispatch:
    def __init__(self, cfg: dict, *, token: str | None = None, session=None, clock=time.time):
        d = (cfg.get("publish") or {}).get("dispatch") or {}
        self.enabled = bool(d.get("enabled", True))
        self.repo = str(d.get("repo") or "KeremKalyoncu/maritime-watch")
        self.workflow = str(d.get("workflow") or "update.yml")
        self.ref = str(d.get("ref") or "main")
        self.every_s = max(10, int(d.get("every_minutes", 30))) * 60
        self.token = (os.getenv("GITHUB_DISPATCH_TOKEN", "") if token is None else token).strip()
        self.session = session
        self.clock = clock
        self.last_ok = 0.0
        self.blocked_until = 0.0

    def due(self) -> bool:
        now = self.clock()
        return (
            self.enabled
            and bool(self.token)
            and now >= self.blocked_until
            and now - self.last_ok >= self.every_s
        )

    def maybe_dispatch(self) -> str | None:
        """None when not due (or no token); else "ok", "refused" (token / permission /
        workflow name, backs off 6 h), "http_<code>" or "error" (retried next cycle)."""
        if not self.due():
            return None
        if self.session is None:
            import requests

            self.session = requests.Session()
        try:
            r = self.session.post(
                API.format(repo=self.repo, workflow=self.workflow),
                json={"ref": self.ref},
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10,
            )
        except Exception as e:  # requests' text may carry headers: type name only
            print(f"[pages] dispatch failed ({type(e).__name__})")
            return "error"
        code = int(getattr(r, "status_code", 0) or 0)
        if 200 <= code < 300:
            self.last_ok = self.clock()
            print("[pages] map rebuild requested on GitHub")
            return "ok"
        if code in (401, 403, 404, 422):
            self.blocked_until = self.clock() + REFUSED_BACKOFF_S
            print(f"[pages] GitHub refused the dispatch ({code}): token, permission or workflow name; next try in 6 h")
            return "refused"
        print(f"[pages] dispatch got HTTP {code}; retry next cycle")
        return f"http_{code}"
