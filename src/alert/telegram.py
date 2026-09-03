"""Telegram output.

Dry-run by default: messages go to the console and data/outbox.log and nothing is
sent. Use --send with TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set to actually post.
Sent message keys are stored in data/sent.json to avoid duplicates.
"""

from __future__ import annotations

import html
import json
import time
from pathlib import Path

import requests

API = "https://api.telegram.org/bot{token}/sendMessage"


class Notifier:
    def __init__(self, cfg: dict):
        self.token = cfg["secrets"]["telegram_token"]
        self.chat = cfg["secrets"]["telegram_chat_id"]
        tcfg = cfg["alert"]["telegram"]
        self.enabled = tcfg.get("enabled", True)
        self.only_status = set(tcfg.get("only_status", ["confirmed"]))
        self.prevention = tcfg.get("prevention", True)

        data_dir = Path(cfg["_root"]) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.outbox = data_dir / "outbox.log"
        self.sent_path = data_dir / "sent.json"
        try:
            self._sent = set(json.loads(self.sent_path.read_text("utf-8")))
        except Exception:
            self._sent = set()

    def _remember(self, key: str) -> None:
        self._sent.add(key)
        self.sent_path.write_text(json.dumps(sorted(self._sent), ensure_ascii=False), encoding="utf-8")

    def _emit(self, key: str, text: str, dry: bool) -> None:
        if key in self._sent:
            return
        with self.outbox.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  [{key}]\n{text}\n{'-' * 60}\n")

        if dry or not self.token or not self.chat:
            first = text.splitlines()[0] if text else ""
            print(f"[telegram:dry] {first}")
            self._remember(key)
            return
        try:
            r = requests.post(
                API.format(token=self.token),
                data={"chat_id": self.chat, "text": text, "parse_mode": "HTML",
                      "disable_web_page_preview": "true"},
                timeout=15,
            )
            ok = r.ok and r.json().get("ok")
            print(f"[telegram] sent={ok} status={r.status_code}")
            if ok:
                self._remember(key)
        except Exception as e:
            print(f"[telegram] error: {e}")

    def incident(self, inc, dry: bool = True) -> None:
        if not self.enabled or inc.status not in self.only_status:
            return
        src = next((s for s in inc.sources if s.kind == "official"),
                   inc.sources[0] if inc.sources else None)
        loc = inc.area or (f"{inc.lat:.3f}, {inc.lon:.3f}" if inc.lat is not None else "konum belirsiz")
        lines = [
            "🚨 <b>Denizde olay (doğrulandı)</b>",
            f"📍 {html.escape(loc)}",
            f"🔎 Tür: {html.escape(inc.type)} · Güven: {inc.confidence}",
        ]
        if inc.casualties:
            lines.append(f"🧍 Bildirilen kişi: {inc.casualties}")
        if src:
            lines.append(f"🏛️ Kaynak: {html.escape(src.org or src.kind)}")
            if src.detail:
                lines.append(html.escape(src.detail[:280]))
            if src.url:
                lines.append(src.url)
        lines.append("\n<i>Otomatik derleme. Resmi açıklamayı esas alın.</i>")
        self._emit(f"inc:{inc.id}:{len(inc.sources)}", "\n".join(lines), dry)

    def warning(self, w, dry: bool = True) -> None:
        if not self.enabled or not self.prevention:
            return
        emoji = "⛔" if w.severity == "major" else "🌊"
        lines = [
            f"{emoji} <b>Denizcilik uyarısı</b>",
            f"📍 {html.escape(w.area or 'Genel')}",
            html.escape(w.headline[:400]),
            f"🏛️ {html.escape(w.org)}",
        ]
        if w.url:
            lines.append(w.url)
        lines.append("\n<i>Resmi uyarı. Denize çıkmadan teyit edin.</i>")
        self._emit(f"wx:{w.id}", "\n".join(lines), dry)
