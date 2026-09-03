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

from ..process.classify import nearest_port

BASE = "https://api.telegram.org/bot{token}/{method}"

_WARN_KIND_TR = {
    "marine-weather": "Denizcilik hava uyarısı",
    "nav-warning": "Seyir uyarısı",
    "navtex": "NAVTEX",
    "earthquake": "Deprem",
    "gdacs": "Afet uyarısı",
    "eonet": "Afet uyarısı",
    "metar": "Kıyı havası",
}
_WARN_EMOJI = {
    "marine-weather": "🌊", "nav-warning": "⚓", "navtex": "⚓",
    "earthquake": "🌍", "gdacs": "🛑", "eonet": "🛑", "metar": "🌬️",
}


class Notifier:
    def __init__(self, cfg: dict):
        self.token = cfg["secrets"]["telegram_token"]
        self.chat = cfg["secrets"]["telegram_chat_id"]
        tcfg = cfg["alert"]["telegram"]
        self.enabled = tcfg.get("enabled", True)
        self.only_status = set(tcfg.get("only_status", ["confirmed"]))
        self.prevention = tcfg.get("prevention", True)
        self.pin = tcfg.get("send_location_pin", True)
        self.site = (cfg.get("site") or {}).get("url", "").rstrip("/")

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

    def _post(self, method: str, data: dict) -> bool:
        try:
            r = requests.post(BASE.format(token=self.token, method=method), data=data, timeout=15)
            body = r.json()
            if r.ok and body.get("ok"):
                return True
            print(f"[telegram] {method} failed status={r.status_code} desc={body.get('description')!r}")
        except Exception as e:
            print(f"[telegram] {method} error: {e}")
        return False

    def _emit(self, key: str, text: str, dry: bool, lat=None, lon=None) -> None:
        if key in self._sent:
            return
        with self.outbox.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  [{key}]\n{text}\n{'-' * 60}\n")

        if dry or not self.token or not self.chat:
            print(f"[telegram:dry] {text.splitlines()[0] if text else ''}")
            self._remember(key)
            return

        ok = self._post("sendMessage", {
            "chat_id": self.chat, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        })
        if ok:
            print(f"[telegram] sent key={key}")
            self._remember(key)
            if self.pin and lat is not None and lon is not None:
                self._post("sendLocation", {"chat_id": self.chat, "latitude": lat, "longitude": lon})

    # ---- shared location block --------------------------------------------
    def _location_lines(self, lat, lon, area, mmsi=None, anchor=None) -> list[str]:
        out = []
        if lat is not None and lon is not None:
            out.append(f"📍 {html.escape(area or '')}  (<code>{lat:.4f}, {lon:.4f}</code>)")
            np = nearest_port(lat, lon)
            if np:
                out.append(f"🧭 {html.escape(np[0])} limanının ~{np[1]:.0f} nM {np[2]}")
            out.append(f"🗺️ https://www.google.com/maps?q={lat:.5f},{lon:.5f}")
            if self.site and anchor:
                out.append(f"🌐 {self.site}/#{anchor}")
            if mmsi:
                out.append(f"🚢 https://www.marinetraffic.com/en/ais/details/ships/mmsi:{mmsi}")
        elif area:
            out.append(f"📍 {html.escape(area)}")
        return out

    # ---- incident -------------------------------------------------------
    def incident(self, inc, dry: bool = True) -> None:
        if not self.enabled:
            return
        is_sart = any(s.kind == "ais-sart" for s in inc.sources)
        if not is_sart and inc.status not in self.only_status:
            return

        head = "🆘 <b>AIS TEHLİKE VERİCİSİ</b>" if is_sart else (
            "🚨 <b>Denizde olay (doğrulandı)</b>" if inc.status == "confirmed"
            else "⚠️ <b>Denizde olay (doğrulanmadı - olası)</b>")
        lines = [head]
        lines += self._location_lines(inc.lat, inc.lon, inc.area, inc.vessel.mmsi, inc.id)
        lines.append(f"🔎 Tür: {html.escape(inc.type)} · Güven: {inc.confidence} · Önem: {html.escape(inc.severity)}")
        if inc.vessel.name:
            lines.append(f"⛴️ Tekne: {html.escape(inc.vessel.name)}"
                         + (f" (MMSI {inc.vessel.mmsi})" if inc.vessel.mmsi else ""))
        if inc.casualties:
            lines.append(f"🧍 Bildirilen kişi: {inc.casualties}")

        lines.append("📚 Kaynaklar:")
        for s in inc.sources[:5]:
            row = f"  • {html.escape(s.kind)}"
            if s.org:
                row += f" / {html.escape(s.org)}"
            if s.detail:
                row += f": {html.escape(s.detail[:200])}"
            lines.append(row)
            if s.url:
                lines.append(f"    {s.url}")

        lines.append("\n<i>Otomatik derleme. Resmi açıklamayı esas alın. Acil: 158 / 112.</i>")
        self._emit(f"inc:{inc.id}:{inc.status}:{len(inc.sources)}", "\n".join(lines), dry,
                   inc.lat, inc.lon)

    # ---- warning ------------------------------------------------------------
    def warning(self, w, dry: bool = True) -> None:
        if not self.enabled or not self.prevention:
            return
        emoji = _WARN_EMOJI.get(w.kind, "⚠️")
        label = _WARN_KIND_TR.get(w.kind, "Uyarı")
        orgs = w.orgs
        lines = [f"{emoji} <b>{label}</b>"]
        lines += self._location_lines(w.lat, w.lon, w.area)
        lines.append(html.escape(w.headline[:400]))
        if len(orgs) >= 2:
            lines.append(f"🏛️ {len(orgs)} kaynak: {html.escape(', '.join(orgs))} · {html.escape(w.severity)}")
        else:
            lines.append(f"🏛️ {html.escape(orgs[0] if orgs else w.org)} · {html.escape(w.severity)}")
        if w.url:
            lines.append(w.url)
        tail = ("Denize çıkmadan teyit edin." if w.kind in ("marine-weather", "metar")
                else "Resmi kaynağı takip edin.")
        lines.append(f"\n<i>{tail}</i>")
        self._emit(f"wx:{w.id}", "\n".join(lines), dry, w.lat, w.lon)

    def warning_confirmed(self, w, dry: bool = True) -> None:
        """A hazard already announced has just picked up an independent source."""
        if not self.enabled or not self.prevention:
            return
        orgs = w.orgs
        emoji = _WARN_EMOJI.get(w.kind, "⚠️")
        label = _WARN_KIND_TR.get(w.kind, "Uyarı")
        lines = [f"✅ {emoji} <b>{label} — {len(orgs)} bağımsız kaynak doğruluyor</b>"]
        lines += self._location_lines(w.lat, w.lon, w.area)
        lines.append(html.escape(w.headline[:300]))
        lines.append(f"🏛️ Kaynaklar: {html.escape(', '.join(orgs))}")
        self._emit(f"wxc:{w.id}:{len(orgs)}", "\n".join(lines), dry, w.lat, w.lon)
