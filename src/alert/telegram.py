"""Telegram output.

Dry-run by default: messages go to the console and data/outbox.log and nothing is
sent. Use --send with TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set to actually post.
Sent message keys are stored in data/sent.json to avoid duplicates.

Messages are written in plain Turkish for a general audience: no English jargon,
no numeric "confidence", one map link, wind in knots + Beaufort.
"""

from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path

import requests

from ..model import status_tr, type_tr
from ..process.classify import nearest_port

BASE = "https://api.telegram.org/bot{token}/{method}"
_SENT_CAP = 5000        # remembered alert keys kept in data/sent.json

_WARN_KIND_TR = {
    "marine-weather": "DENİZ HAVA UYARISI",
    "metar": "KIYI HAVA UYARISI",
    "nav-warning": "SEYİR UYARISI",
    "navtex": "SEYİR UYARISI (NAVTEX)",
    "earthquake": "DEPREM",
    "gdacs": "AFET UYARISI",
    "eonet": "AFET UYARISI",
}
_WARN_EMOJI = {
    "marine-weather": "🌊", "metar": "🌬️", "nav-warning": "⚓", "navtex": "⚓",
    "earthquake": "🌍", "gdacs": "🛑", "eonet": "🛑",
}
def _num(x) -> str:
    """Turkish decimal comma, trimmed."""
    s = f"{x:.1f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _beaufort(kn: float) -> int:
    for b, top in enumerate([1, 3, 6, 10, 16, 21, 27, 33, 40, 47, 55, 63]):
        if kn <= top:
            return b
    return 12


class Notifier:
    def __init__(self, cfg: dict):
        self.token = cfg["secrets"]["telegram_token"]
        self.chat = cfg["secrets"]["telegram_chat_id"]
        tcfg = cfg["alert"]["telegram"]
        self.enabled = tcfg.get("enabled", True)
        self.only_status = set(tcfg.get("only_status", ["confirmed"]))
        self.prevention = tcfg.get("prevention", True)
        self.pin = tcfg.get("send_location_pin", True)
        self.digest = tcfg.get("digest", True)      # one combined message per cycle
        self.site = (cfg.get("site") or {}).get("url", "").rstrip("/")

        data_dir = Path(cfg["_root"]) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.outbox = data_dir / "outbox.log"
        self.sent_path = data_dir / "sent.json"
        try:
            self._sent = set(json.loads(self.sent_path.read_text("utf-8")))
        except Exception:
            self._sent = set()
        self._queue: list[tuple] = []              # (key, text, lat, lon) pending digest

    def _remember(self, key: str) -> None:
        self._sent.add(key)
        # this file is committed between CI runs, so keep it bounded
        if len(self._sent) > _SENT_CAP:
            self._sent = set(sorted(self._sent)[-_SENT_CAP:])
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

    def _send_one(self, key: str, text: str, dry: bool, lat=None, lon=None) -> None:
        if dry or not self.token or not self.chat:
            print(f"[telegram:dry] {text.splitlines()[0] if text else ''}")
            self._remember(key)
            return
        if self._post("sendMessage", {
            "chat_id": self.chat, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }):
            print(f"[telegram] sent key={key}")
            self._remember(key)
            if self.pin and lat is not None and lon is not None:
                self._post("sendLocation", {"chat_id": self.chat, "latitude": lat, "longitude": lon})

    def _emit(self, key: str, text: str, dry: bool, lat=None, lon=None, urgent: bool = False) -> None:
        if key in self._sent or any(k == key for k, *_ in self._queue):
            return
        with self.outbox.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  [{key}]\n{text}\n{'-' * 60}\n")

        if urgent or not self.digest:
            self._send_one(key, text, dry, lat, lon)
        else:
            self._queue.append((key, text, lat, lon))

    def flush(self, dry: bool = True) -> None:
        """Send everything queued this cycle as one message (or a few if long)."""
        if not self._queue:
            return
        q, self._queue = self._queue, []
        stamp = time.strftime("%H:%M")
        blocks = [f"🔔 <b>{len(q)} yeni bildirim · {stamp}</b>"]
        for _k, text, _la, _lo in q:
            head = []
            for line in text.splitlines():
                if line.startswith("<i>") or line.startswith("📚"):
                    break
                head.append(line)
            blocks.append("\n".join(head).strip())

        sep = "\n\n➖➖➖➖➖\n\n"
        chunks, cur = [], blocks[0]
        for b in blocks[1:]:
            if len(cur) + len(sep) + len(b) > 3800:
                chunks.append(cur)
                cur = b
            else:
                cur += sep + b
        chunks.append(cur)

        keys = [k for k, *_ in q]
        with self.outbox.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  [DIGEST {len(q)} items]\n"
                    + f"\n\n{'=' * 60}\n\n".join(chunks) + f"\n{'-' * 60}\n")
        if dry or not self.token or not self.chat:
            print(f"[telegram:dry] digest: {len(q)} bildirim, {len(chunks)} mesaj")
            for k in keys:
                self._remember(k)
            return
        sent_any = False
        for c in chunks:
            if self._post("sendMessage", {"chat_id": self.chat, "text": c,
                                          "parse_mode": "HTML", "disable_web_page_preview": "true"}):
                sent_any = True
        if sent_any:
            print(f"[telegram] digest sent ({len(q)} items)")
            for k in keys:
                self._remember(k)

    def _where(self, lat, lon, area, coarse: bool = False) -> str:
        """One plain-language 'where' line. A city-name geocode is reported as
        "X açıkları" rather than a meaningless "~0 deniz mili" distance."""
        if lat is None or lon is None:
            return f"📍 Yer: {html.escape(area or 'belirtilmedi')}"
        np = nearest_port(lat, lon)
        if not np:
            return f"📍 Yer: {html.escape(area or '')}"
        if coarse or np[1] < 2:
            where = f"{html.escape(np[0])} açıkları"
            return f"📍 Yer: {where}" + (f" ({html.escape(area)})" if area else "")
        return (f"📍 Yer: {html.escape(area or '')} — en yakın kıyı: "
                f"{html.escape(np[0])} (~{np[1]:.0f} deniz mili)")

    def _maplink(self, lat, lon) -> str:
        return f"🗺️ Haritada gör: https://www.google.com/maps?q={lat:.5f},{lon:.5f}"

    # ---- incident --------------------------------------------------------
    def incident(self, inc, dry: bool = True) -> None:
        if not self.enabled:
            return
        is_sart = any(s.kind == "ais-sart" for s in inc.sources)
        if not is_sart and inc.status not in self.only_status:
            return

        if is_sart:
            head = "🆘 <b>TEHLİKE İŞARETİ ALINDI</b>\nBir teknenin otomatik imdat vericisi sinyal veriyor."
        elif inc.status == "confirmed":
            head = "🚨 <b>DENİZDE OLAY — DOĞRULANDI</b>"
        else:
            head = "⚠️ <b>DENİZDE OLAY — henüz doğrulanmadı</b>"

        lines = [head, ""]
        lines.append(f"Ne oldu: {html.escape(type_tr(inc.type))}")
        lines.append(self._where(inc.lat, inc.lon, inc.area, getattr(inc, 'coarse', False)))
        if inc.vessel.name:
            lines.append(f"⛴️ Tekne: {html.escape(inc.vessel.name)}")
        told = [s for s in inc.sources if s.detail and s.kind in ("official", "news")]
        if inc.casualties:
            suffix = " (kaynaklarda geçen en yüksek sayı)" if len(told) > 1 else ""
            lines.append(f"🧍 {inc.casualties} kişi bildirildi{suffix}")
        lines.append(f"Durum: {html.escape(status_tr(inc.status))}")

        lines.append("")
        if len(told) > 1:
            lines.append(f"Kaynaklar ({len(told)}):")
        for s in told[:3]:
            org = html.escape(s.org or s.kind)
            lines.append(f"• {org}: “{html.escape(s.detail[:180])}”")
            if s.url:
                lines.append(f"  {s.url}")
        if len(told) > 3:
            lines.append(f"…ve {len(told) - 3} kaynak daha")
        if not told:
            first = inc.sources[0] if inc.sources else None
            if first:
                lines.append(f"Kaynak: {html.escape(first.org or first.kind)}"
                             + (f" — {html.escape(first.detail[:180])}" if first.detail else ""))

        if inc.lat is not None and inc.lon is not None:
            lines.append(self._maplink(inc.lat, inc.lon))

        lines.append("")
        lines.append("<i>Bu otomatik bir derlemedir; resmi açıklamayı esas alın.</i>")
        lines.append("<b>Acil durumda: 158 Sahil Güvenlik  ·  112</b>")
        self._emit(f"inc:{inc.id}:{inc.status}:{len(inc.sources)}", "\n".join(lines), dry,
                   inc.lat, inc.lon, urgent=is_sart)

    # ---- warning -------------------------------------------------------------
    def _weather_body(self, w) -> list[str]:
        out = []
        wave = None
        if w.value:
            wave = w.value
            out.append(f"Dalga: {_num(wave)} metreye çıkıyor")
        # pull a gust number out of the headline if present
        m = re.search(r"(\d+)\s*kn", w.headline)
        if m:
            kn = float(m.group(1))
            out.append(f"Rüzgar: {int(kn)} knota ({_beaufort(kn)} Bofor) çıkıyor")
        if not out:
            out.append(html.escape(w.headline[:200]))
        return out

    def warning(self, w, dry: bool = True) -> None:
        if not self.enabled or not self.prevention:
            return
        emoji = _WARN_EMOJI.get(w.kind, "⚠️")
        label = _WARN_KIND_TR.get(w.kind, "UYARI")
        orgs = w.orgs
        lines = [f"{emoji} <b>{label}</b>", ""]
        lines.append(f"Bölge: {html.escape(w.area or 'genel')}")

        if w.kind in ("marine-weather", "metar"):
            lines += self._weather_body(w)
        elif w.kind == "earthquake":
            lines.append(f"Büyüklük: {_num(w.value)}" if w.value else html.escape(w.headline[:200]))
        else:
            lines.append(html.escape(w.headline[:240]))

        if len(orgs) >= 2:
            lines.append(f"✅ {len(orgs)} kaynak doğruluyor: {html.escape(', '.join(orgs))}")
        else:
            lines.append(f"Kaynak: {html.escape(orgs[0] if orgs else w.org)}")

        if w.lat is not None and w.lon is not None:
            lines.append(self._maplink(w.lat, w.lon))

        lines.append("")
        if w.kind in ("marine-weather", "metar"):
            lines.append("<b>Küçük tekneyle denize çıkmayın.</b> Çıkmadan önce liman "
                         "başkanlığından / MGM'den teyit alın.")
        elif w.kind == "earthquake":
            lines.append("<i>Kıyıya yakın deprem. Deniz seviyesi değişimlerine dikkat.</i>")
        else:
            lines.append("<i>Resmi kaynağı takip edin.</i>")
        self._emit(f"wx:{w.id}", "\n".join(lines), dry, w.lat, w.lon)

    def operator(self, text: str, dry: bool = True) -> None:
        """System health notice. Sent once per day per distinct message."""
        if not self.enabled:
            return
        key = "ops:" + time.strftime("%Y-%m-%d") + ":" + str(abs(hash(text)) % 100000)
        self._emit(key, f"{html.escape(text)}", dry, urgent=True)

    def warning_confirmed(self, w, dry: bool = True) -> None:
        if not self.enabled or not self.prevention:
            return
        orgs = w.orgs
        label = _WARN_KIND_TR.get(w.kind, "UYARI")
        lines = [
            f"✅ <b>DOĞRULANDI — {len(orgs)} ayrı kaynak aynı uyarıyı veriyor</b>",
            "",
            f"Konu: {label.capitalize()}",
            f"Bölge: {html.escape(w.area or 'genel')}",
            html.escape(w.headline[:220]),
            f"Kaynaklar: {html.escape(', '.join(orgs))}",
        ]
        if w.lat is not None and w.lon is not None:
            lines.append(self._maplink(w.lat, w.lon))
        self._emit(f"wxc:{w.id}:{len(orgs)}", "\n".join(lines), dry, w.lat, w.lon)
