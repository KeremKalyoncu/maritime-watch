"""Interactive Telegram bot: each person gets their own areas and boat class.

A single broadcast channel sends a Marmara fisherman thirteen sea areas they do
not care about, and one threshold that fits nobody in particular. Here each chat
picks its own areas and boat size, and the morning message is built for it.

Two deployment shapes, and the difference matters:

  --loop on a host   getUpdates runs every cycle, so a command is answered in
                     seconds. This is the mode the bot is for.
  cron only          replies would wait for the next scheduled run (~15 min),
                     which is not a conversation. Daily pushes still work.

PRIVACY: a chat id identifies a person, so data/subscribers.json is git-ignored
and never leaves the host. Nothing about a subscriber reaches the public repo,
the map or the feed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

BASE = "https://api.telegram.org/bot{token}/{method}"

HELP = """<b>Maritime Watch</b> — küçük tekne için deniz durumu

Her sabah, seçtiğin bölgeler için saat saat durum gönderirim.

<b>Komutlar</b>
/bolge — takip ettiğin denizleri seç
/tekne — tekne boyunu seç (eşikler buna göre)
/durum — şu anki tahmini hemen gönder
/ayarlar — mevcut ayarların
/dur — bildirimleri kapat
/yardim — bu mesaj

<i>Model tahminidir, ölçüm değildir. Karar senindir; çıkmadan önce liman
başkanlığından ve MGM'den teyit al.</i>
<b>Acil durumda: 158 Sahil Güvenlik · 112</b>"""

WELCOME = """⚓ <b>Hoş geldin.</b>

Sana her sabah <b>06:00'da</b> takip ettiğin denizler için
<b>bugün çıkabilir misin, saat kaça kadar</b> sorusunun cevabını göndereceğim.

Önce iki şey seçelim:
1️⃣ /bolge — hangi denizleri takip ediyorsun
2️⃣ /tekne — teknenin boyu (eşikler buna göre değişir)

Seçmezsen varsayılan: <b>tüm bölgeler</b>, <b>8 m ve altı tekne</b>."""


class Subscribers:
    """Per-chat settings. Kept off the public repo on purpose."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.data: dict[str, dict] = {}
        self.offset: int = 0
        if self.path.exists():
            try:
                blob = json.loads(self.path.read_text("utf-8") or "{}")
                self.data = blob.get("chats", {})
                self.offset = int(blob.get("offset", 0))
            except (json.JSONDecodeError, ValueError):
                pass

    def get(self, chat_id) -> dict:
        return self.data.setdefault(str(chat_id), {
            "areas": [], "boat": "small", "active": True, "since": _now(),
        })

    def active(self) -> list[tuple[str, dict]]:
        return [(c, s) for c, s in sorted(self.data.items()) if s.get("active", True)]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [json.dumps(k) + ":" + json.dumps(v, ensure_ascii=False, sort_keys=True)
                for k, v in sorted(self.data.items())]
        self.path.write_text(
            '{"offset":' + str(self.offset) + ',"chats":{' + ",\n".join(rows) + "}}",
            encoding="utf-8")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _keyboard(rows: list[list[str]]) -> str:
    return json.dumps({"inline_keyboard": [
        [{"text": t, "callback_data": d} for t, d in row] for row in rows]})


class Bot:
    def __init__(self, cfg: dict, notifier=None):
        self.cfg = cfg
        self.token = cfg["secrets"].get("telegram_token", "")
        self.notifier = notifier
        root = Path(cfg["_root"])
        self.subs = Subscribers(str(root / "data" / "subscribers.json"))
        self.areas = [p["name"] for p in cfg["openmeteo"]["points"]]
        self.classes = cfg.get("outlook", {}).get("classes", {})

    # ---- transport -----------------------------------------------------------
    def _api(self, method: str, payload: dict, timeout: int = 20):
        if not self.token:
            return None
        try:
            r = requests.post(BASE.format(token=self.token, method=method),
                              data=payload, timeout=timeout)
            body = r.json()
            if body.get("ok"):
                return body.get("result")
            print(f"[bot] {method} reddedildi: {body.get('description')!r}")
        except Exception as e:
            print(f"[bot] {method} error: {e}")
        return None

    def send(self, chat_id, text: str, markup: str | None = None, dry: bool = True) -> bool:
        if dry or not self.token:
            print(f"[bot:dry] -> {chat_id}: {text.splitlines()[0] if text else ''}")
            return True
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": "true"}
        if markup:
            payload["reply_markup"] = markup
        return self._api("sendMessage", payload) is not None

    # ---- menus ---------------------------------------------------------------
    def _area_markup(self, chosen: list[str]) -> str:
        rows, row = [], []
        for i, a in enumerate(self.areas):
            mark = "✅" if (not chosen or a in chosen) else "▫️"
            row.append((f"{mark} {a}", f"area:{i}"))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([("🌍 Hepsi", "area:all"), ("✔️ Tamam", "area:done")])
        return _keyboard(rows)

    def _boat_markup(self, chosen: str) -> str:
        rows = [[(("✅ " if k == chosen else "") + v.get("label", k), f"boat:{k}")]
                for k, v in self.classes.items()]
        return _keyboard(rows)

    def _settings_text(self, s: dict) -> str:
        areas = ", ".join(s.get("areas") or []) or "tüm bölgeler"
        klass = self.classes.get(s.get("boat", "small"), {}).get("label", s.get("boat"))
        state = "açık" if s.get("active", True) else "kapalı"
        return (f"⚙️ <b>Ayarların</b>\n\n"
                f"🌊 Bölgeler: <b>{areas}</b>\n"
                f"⛵ Tekne: <b>{klass}</b>\n"
                f"🔔 Bildirim: <b>{state}</b>\n\n"
                f"Değiştirmek için /bolge veya /tekne.")

    # ---- command handling ----------------------------------------------------
    def handle(self, update: dict, dry: bool = True) -> None:
        msg = update.get("message") or {}
        cb = update.get("callback_query")
        if cb:
            return self._on_callback(cb, dry)
        text = (msg.get("text") or "").strip().lower()
        chat = (msg.get("chat") or {}).get("id")
        if not chat or not text:
            return
        s = self.subs.get(chat)
        cmd = text.split()[0].lstrip("/").split("@")[0]

        if cmd in ("start", "basla"):
            s["active"] = True
            self.send(chat, WELCOME, dry=dry)
        elif cmd in ("yardim", "help", "yardım"):
            self.send(chat, HELP, dry=dry)
        elif cmd in ("bolge", "bölge", "bolgeler"):
            self.send(chat, "🌊 <b>Hangi denizleri takip ediyorsun?</b>\nSeçtikçe değişir; "
                            "hiçbiri seçili değilse hepsini gönderirim.",
                      self._area_markup(s.get("areas", [])), dry=dry)
        elif cmd in ("tekne", "boat"):
            self.send(chat, "⛵ <b>Tekne boyun?</b>\nUyarı eşikleri buna göre değişir.",
                      self._boat_markup(s.get("boat", "small")), dry=dry)
        elif cmd in ("ayarlar", "ayar"):
            self.send(chat, self._settings_text(s), dry=dry)
        elif cmd in ("durum", "simdi", "şimdi"):
            self.send_outlook_now(chat, s, dry=dry)
        elif cmd in ("dur", "stop", "kapat"):
            s["active"] = False
            self.send(chat, "🔕 Bildirimler kapatıldı. Tekrar açmak için /start.", dry=dry)
        else:
            self.send(chat, "Bu komutu bilmiyorum.\n\n" + HELP, dry=dry)
        self.subs.save()

    def _on_callback(self, cb: dict, dry: bool) -> None:
        chat = ((cb.get("message") or {}).get("chat") or {}).get("id")
        data = cb.get("data") or ""
        if not chat:
            return
        s = self.subs.get(chat)
        note = ""
        if data.startswith("area:"):
            key = data.split(":", 1)[1]
            if key == "all":
                s["areas"] = []
                note = "Tüm bölgeler"
            elif key == "done":
                note = "Kaydedildi"
            elif key.isdigit() and int(key) < len(self.areas):
                a = self.areas[int(key)]
                cur = list(s.get("areas") or [])
                cur.remove(a) if a in cur else cur.append(a)
                s["areas"] = cur
                note = a
            if key != "done":
                self._api("editMessageReplyMarkup", {
                    "chat_id": chat, "message_id": (cb.get("message") or {}).get("message_id"),
                    "reply_markup": self._area_markup(s.get("areas", []))}) if not dry else None
            else:
                self.send(chat, self._settings_text(s), dry=dry)
        elif data.startswith("boat:"):
            k = data.split(":", 1)[1]
            if k in self.classes:
                s["boat"] = k
                note = self.classes[k].get("label", k)
            self.send(chat, self._settings_text(s), dry=dry)
        if not dry:
            self._api("answerCallbackQuery", {"callback_query_id": cb.get("id"), "text": note})
        self.subs.save()

    # ---- outlook -------------------------------------------------------------
    def send_outlook_now(self, chat, s: dict, dry: bool = True) -> None:
        """Answer /durum on demand. Built fresh, never from cached fixtures."""
        if self.notifier is None:
            return
        text = self.notifier.outlook_text_for(self.cfg, s)
        self.send(chat, text or "Şu an canlı tahmin alınamıyor, biraz sonra tekrar dene.", dry=dry)

    # ---- polling -------------------------------------------------------------
    def poll(self, dry: bool = True, limit: int = 50) -> int:
        """Drain pending updates. Offset is persisted so a restart does not
        replay yesterday's commands."""
        if not self.token:
            return 0
        res = self._api("getUpdates", {"offset": self.subs.offset + 1,
                                       "limit": limit, "timeout": 0})
        if not res:
            return 0
        for up in res:
            self.subs.offset = max(self.subs.offset, int(up.get("update_id", 0)))
            try:
                self.handle(up, dry=dry)
            except Exception as e:
                print(f"[bot] update islenemedi: {e}")
        self.subs.save()
        return len(res)
