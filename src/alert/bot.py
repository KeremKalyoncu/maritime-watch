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

import html
import json
import math
import time
from pathlib import Path

import requests

try:
    from ..geo import area_of
    from ..process.classify import PORTS, _haversine_nm, _norm, nearest_port
except (ImportError, ValueError):
    from src.geo import area_of
    from src.process.classify import PORTS, _haversine_nm, _norm, nearest_port

BASE = "https://api.telegram.org/bot{token}/{method}"

HELP = """⚓ <b>Maritime Watch Türkiye</b>
<i>Bugün çıkabilir miyim? — tekne boyuna göre.</i>

<b>Denize çıkış</b>
🎣 /balikci — Bugün saatlik pencere + limana dönüş
🌊 /durum — Anlık hava (seçili bölgeler)
🚢 /bogaz — İstanbul &amp; Çanakkale canlı durum
🚨 /kazalar — Onaylı kaza / kurtarma

<b>Seyir &amp; acil</b>
📍 /neredeyim — En yakın liman (konum paylaş)
🆘 /mayday — VHF 16 hazır imdat metni

<b>Ayarlar</b>
⚙️ /bolge · ⛵ /tekne · 📋 /ayarlar
🔕 /dur — bildirimleri kapat

<i>Model tahminidir. Karar senindir · 158 · 151 · VHF 16</i>"""

WELCOME = """⚓ <b>Hoş geldin — Maritime Watch</b>

Her sabah <b>06:00</b>’da sana özel cevap:
<b>«Bugün çıkabilir miyim, saat kaça kadar?»</b>

Alttaki menüden tek dokunuşla kullan; ya da önce ayarla:
1️⃣ <b>Bölge</b> — hangi denizler
2️⃣ <b>Tekne</b> — boy (eşikler buna göre)

Seçmezsen: <b>tüm bölgeler</b>, <b>≤8 m tekne</b>."""

# Persistent reply keyboard — one tap for skippers (no slash typing at sea)
MAIN_KEYBOARD_ROWS = [
    [("🎣 Bugün",), ("🌊 Durum",), ("🚢 Boğaz",)],
    [("🚨 Kazalar",), ("📍 Neredeyim",), ("🆘 Mayday",)],
    [("⚙️ Bölge",), ("⛵ Tekne",), ("📋 Ayarlar",)],
]

# Map reply-keyboard labels → command tokens (keys via _norm at lookup time)
_KEYBOARD_CMD_BY_LABEL = {
    "🎣 Bugün": "balikci",
    "🌊 Durum": "durum",
    "🚢 Boğaz": "bogaz",
    "🚨 Kazalar": "kazalar",
    "📍 Neredeyim": "neredeyim",
    "🆘 Mayday": "mayday",
    "⚙️ Bölge": "bolge",
    "⛵ Tekne": "tekne",
    "📋 Ayarlar": "ayarlar",
}


def _keyboard_command(text: str) -> str | None:
    """Resolve a reply-keyboard tap (or plain synonym) to a command name."""
    low = _norm(text).strip()
    for label, cmd in _KEYBOARD_CMD_BY_LABEL.items():
        if _norm(label) == low:
            return cmd
    synonyms = {
        "bugun": "balikci", "bugün": "balikci",
        "menu": "yardim", "menü": "yardim", "yardim": "yardim", "yardım": "yardim",
    }
    return synonyms.get(low)


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

        # Keep data/bot_subscribers.json synchronized with regional subscriptions
        bot_sub_path = self.path.parent / "bot_subscribers.json"
        reg_map: dict[str, list[str]] = {}
        for cid, info in self.data.items():
            if info.get("active", True):
                for a in info.get("areas") or []:
                    reg_map.setdefault(a, []).append(str(cid))
        bot_sub_data = {
            "offset": self.offset,
            "chats": self.data,
            "regions": reg_map,
            **reg_map,
        }
        bot_sub_path.write_text(
            json.dumps(bot_sub_data, ensure_ascii=False, indent=2),
            encoding="utf-8")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _keyboard(rows: list[list[str]]) -> str:
    return json.dumps({"inline_keyboard": [
        [{"text": t, "callback_data": d} for t, d in row] for row in rows]})


def _reply_keyboard() -> str:
    """Bottom menu — resize + persistent so it stays after restart."""
    return json.dumps({
        "keyboard": [[{"text": cell[0]} for cell in row] for row in MAIN_KEYBOARD_ROWS],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "Komut seç veya yaz…",
    }, ensure_ascii=False)


def _inline_home_menu() -> str:
    """Quick actions under /yardim (works even if reply keyboard hidden)."""
    return _keyboard([
        [("🎣 Bugün", "menu:balikci"), ("🌊 Durum", "menu:durum")],
        [("🚢 Boğaz", "menu:bogaz"), ("🚨 Kazalar", "menu:kazalar")],
        [("📍 Neredeyim", "menu:neredeyim"), ("🆘 Mayday", "menu:mayday")],
        [("⚙️ Bölge", "menu:bolge"), ("⛵ Tekne", "menu:tekne")],
        [("📋 Ayarlar", "menu:ayarlar")],
    ])


def _outlook_stale_hours(cfg: dict) -> float:
    oc = cfg.get("outlook") or {}
    if oc.get("stale_hours") is not None:
        return float(oc["stale_hours"])
    return float((cfg.get("alert") or {}).get("stale_hours", 2))


def _outlook_age_hours(generated: str | None) -> float | None:
    if not generated:
        return None
    try:
        # Accept …Z or +00:00
        raw = str(generated).strip().replace("Z", "+00:00")
        from datetime import datetime
        dt = datetime.fromisoformat(raw)
        return max(0.0, (time.time() - dt.timestamp()) / 3600.0)
    except (TypeError, ValueError):
        return None


def _stale_banner(cfg: dict, generated: str | None) -> str:
    age = _outlook_age_hours(generated)
    if age is None:
        return ""
    limit = _outlook_stale_hours(cfg)
    if age <= limit:
        return ""
    return f"⚠ <b>Eski tahmin</b> (~{age:.0f}s) — cycle gecikmiş olabilir.\n\n"


def _area_matches_warning(area: str, warn_area: str) -> bool:
    a, w = _norm(area), _norm(warn_area or "")
    if not a or not w:
        return False
    return a in w or w in a or w.split()[0] in a


def _official_warnings_for_area(root: Path, area: str, limit: int = 2) -> list[str]:
    path = root / "web" / "data" / "warnings.json"
    if not path.exists():
        return []
    try:
        blob = json.loads(path.read_text("utf-8") or "[]")
    except (json.JSONDecodeError, OSError):
        return []
    rows = blob if isinstance(blob, list) else blob.get("warnings") or []
    out: list[str] = []
    for w in rows:
        if not isinstance(w, dict):
            continue
        if not _area_matches_warning(area, w.get("area") or ""):
            # Also match coarse sea names inside headline (MGM often omits area field detail)
            head = w.get("headline") or ""
            if not _area_matches_warning(area, head):
                continue
        org = (w.get("org") or "").upper()
        srcs = w.get("sources") or []
        is_official = (
            "MGM" in org
            or any("MGM" in str((s or {}).get("org", "")).upper() for s in srcs if isinstance(s, dict))
            or (w.get("kind") or "") in ("marine-weather", "metar")
        )
        if not is_official:
            continue
        title = (w.get("headline") or "").strip()
        if title:
            out.append(title)
        if len(out) >= limit:
            break
    return out


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.cos(math.radians(lon2 - lon1)))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


class Bot:
    def __init__(self, cfg: dict, notifier=None):
        self.cfg = cfg
        self.token = cfg["secrets"].get("telegram_token", "")
        self.notifier = notifier
        root = Path(cfg["_root"])
        self.subs = Subscribers(str(root / "data" / "subscribers.json"))
        self.areas = [p["name"] for p in cfg.get("openmeteo", {}).get("points", [])]
        self.classes = cfg.get("outlook", {}).get("classes", {})
        self.session = requests.Session()
        self._commands_registered = False

    def register_commands(self) -> bool:
        """Register the official '/' command menu (short labels for mobile)."""
        if not self.token:
            return False
        # Order = priority for fishermen; keep descriptions ≤ ~40 chars
        commands = [
            {"command": "balikci", "description": "🎣 Bugün çıkılır mı? Saatlik pencere"},
            {"command": "durum", "description": "🌊 Anlık deniz havası"},
            {"command": "bogaz", "description": "🚢 Boğazlar — gemi & sis"},
            {"command": "kazalar", "description": "🚨 Onaylı kaza / kurtarma"},
            {"command": "neredeyim", "description": "📍 En yakın liman (konum)"},
            {"command": "mayday", "description": "🆘 VHF 16 imdat metni"},
            {"command": "bolge", "description": "⚙️ Takip edilen denizler"},
            {"command": "tekne", "description": "⛵ Tekne boyu / eşikler"},
            {"command": "ayarlar", "description": "📋 Kayıtlı ayarların"},
            {"command": "yardim", "description": "ℹ️ Menü ve kullanım"},
            {"command": "dur", "description": "🔕 Bildirimleri kapat"},
        ]
        res = self._api("setMyCommands", {"commands": json.dumps(commands, ensure_ascii=False)})
        return res is not None

    # ---- transport -----------------------------------------------------------
    def _api(self, method: str, payload: dict, timeout: int = 20):
        if not self.token:
            return None
        try:
            r = self.session.post(BASE.format(token=self.token, method=method),
                                  data=payload, timeout=timeout)
            body = r.json()
            if body.get("ok"):
                return body.get("result")
            # description can echo the bot token; error_code is enough to debug
            print(f"[bot] {method} reddedildi: error_code={body.get('error_code')}")
        except Exception as e:
            # requests may put the request URL (with token) into the exception text
            print(f"[bot] {method} error: {type(e).__name__}")
        return None

    def send(self, chat_id, text: str, markup: str | None = None, dry: bool = True) -> bool:
        if dry or not self.token:
            first_line = text.splitlines()[0] if text else ""
            try:
                # chat_id identifies a person — never clear-text in logs
                print(f"[bot:dry] {first_line}")
            except UnicodeEncodeError:
                safe_line = first_line.encode("ascii", errors="backslashreplace").decode("ascii")
                print(f"[bot:dry] {safe_line}")
            return True
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": "true"}
        if markup:
            payload["reply_markup"] = markup
        return self._api("sendMessage", payload) is not None

    # ---- menus & matching ----------------------------------------------------
    def _match_area(self, text: str) -> str | None:
        norm_txt = _norm(text).strip()
        if not norm_txt:
            return None
        # 1. Exact normalized match
        for a in self.areas:
            if _norm(a) == norm_txt:
                return a
        # 2. Substring match (e.g. "marmara" in "marmara denizi")
        for a in self.areas:
            if norm_txt in _norm(a) or _norm(a) in norm_txt:
                return a
        # 3. Word-by-word match
        words = norm_txt.split()
        for a in self.areas:
            a_norm = _norm(a)
            if all(w in a_norm for w in words):
                return a
        return None

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

    def _handle_location(self, chat, lat: float, lon: float, dry: bool = True) -> None:
        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            self.send(chat, "❌ Geçersiz koordinat formatı. Örnek: <code>/neredeyim 38.3245 26.3012</code>", dry=dry)
            return

        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            self.send(chat, "❌ Koordinatlar geçerli dünya sınırları dışında.", dry=dry)
            return

        port_info = nearest_port(lat, lon)
        if not port_info:
            port_line = "⚓ <b>En Yakın Liman:</b> Belirlenemedi"
        else:
            p_name, dist_nm, _ = port_info
            pla, plo = PORTS.get(p_name, (lat, lon))
            b_deg = _bearing_deg(lat, lon, pla, plo)
            port_label = p_name if p_name.lower().endswith("limanı") or p_name.lower().endswith("liman") else f"{p_name} Limanı"
            port_line = f"⚓ <b>En Yakın Liman:</b> {port_label} ({dist_nm:.1f} NM, {b_deg:03.0f}°)"

        # Area & closest forecast point
        area_name = area_of(lat, lon) or ""
        closest_pt = None
        min_d = float("inf")
        for pt in self.cfg.get("openmeteo", {}).get("points", []):
            d = _haversine_nm(lat, lon, pt["lat"], pt["lon"])
            if d < min_d:
                min_d = d
                closest_pt = pt

        if not area_name and closest_pt:
            area_name = closest_pt["name"]
        if not area_name:
            area_name = "Kıyı Bölgesi"

        # Lookup safety index rating if available
        safety_file = Path(self.cfg["_root"]) / "web" / "data" / "safety_index.json"
        rating_info = None
        if safety_file.exists():
            try:
                s_data = json.loads(safety_file.read_text("utf-8") or "{}")
                target_area = closest_pt["name"] if closest_pt else area_name
                for r in s_data.get("ratings", []):
                    if r.get("area") == target_area:
                        rating_info = r
                        break
            except Exception:
                pass

        if rating_info:
            score = rating_info.get("score")
            status = rating_info.get("status") or ""
            quality = rating_info.get("data_quality") or "ok"
            if score is None or status in ("", "unknown") or quality == "unknown":
                safety_line = "🌊 <b>Sefer skoru:</b> veri yok (ölçüm eksik / henüz derlenmedi)"
            else:
                icon = "🟢" if status == "good" else ("🟡" if status == "caution" else "🔴")
                status_tr = "Elverişli" if status == "good" else (
                    "Tedbirli Seyir" if status == "caution" else "Denize Çıkmayın")
                safety_line = f"🌊 <b>Sefer Güvenlik Skoru:</b> {icon} {score}/100 ({status_tr})"
                st = rating_info.get("sea_temp_c")
                ck = rating_info.get("current_kn")
                if st is not None:
                    safety_line += f"\n🌡️ <b>Deniz Suyu:</b> {st:.1f}°C" + (
                        f" | <b>Akıntı:</b> {ck:.1f} kn" if ck is not None else "")
        else:
            safety_line = "🌊 <b>Sefer skoru:</b> veri yok (henüz derlenmedi)"

        # Store last known location for subsequent /mayday calls
        s = self.subs.get(chat)
        s["last_location"] = {"lat": lat, "lon": lon, "time": _now()}

        text = (
            f"📍 <b>Konumunuz:</b> {area_name} ({lat:.4f}°K, {lon:.4f}°D)\n"
            f"{port_line}\n"
            f"{safety_line}\n"
            f"📞 <b>Sahil Güvenlik:</b> 158 | <b>Acil:</b> 112 | <b>VHF:</b> Kanal 16"
        )
        self.send(chat, text, dry=dry)

    def _mayday_text(self, s: dict) -> str:
        loc = s.get("last_location")
        if loc:
            lat, lon = loc["lat"], loc["lon"]
            p_info = nearest_port(lat, lon)
            if p_info:
                p_name, dist_nm, _ = p_info
                p_lbl = p_name if p_name.lower().endswith("limanı") or p_name.lower().endswith("liman") else f"{p_name} Limanı"
                mevki = f"{lat:.4f}°K, {lon:.4f}°D ({p_lbl} {dist_nm:.1f} NM açığı)"
            else:
                mevki = f"{lat:.4f}°K, {lon:.4f}°D"
        else:
            mevki = "[ENLEM, BOYLAM veya MEVKİNİZİ SÖYLEYİN (örn: Çeşme 3 mil açığı)]"

        return (
            "🆘 <b>VHF KANAL 16 ACİL İMDAT ÇAĞRISI (MAYDAY)</b>\n\n"
            "<i>Telsizin mandalına basarak 3 kez, tane tane ve anlaşılır bir ses tonuyla okuyun:</i>\n\n"
            "<b>\"MAYDAY, MAYDAY, MAYDAY\n"
            "BURASI [TEKNE ADINIZ / ÇAĞRI İŞARETİNİZ]\n"
            f"MEVKİMİZ: {mevki}\n"
            "DURUM: [SU ALIYORUZ / BATIYORUZ / ALABORA OLDUK / YANGIN VAR]\n"
            "TEKNEDE [X] KİŞİYİZ, ACİL KURTARMA TALEP EDİYORUZ.\n"
            "TAMAM.\"</b>\n\n"
            "📞 <b>TELEFON İLE ACİL YARDIM HATLARI:</b>\n"
            "• <b>158</b> Sahil Güvenlik (7/24 Kesintisiz)\n"
            "• <b>151</b> Kıyı Emniyeti (Tahlisiye & Römorkör)\n"
            "• <b>112</b> Acil Çağrı Merkezi\n"
            "• <b>VHF Ch 16</b> (156.800 MHz Uluslararası Tehlike & Çağrı)"
        )

    def _straits_text(self) -> str:
        straits_file = Path(self.cfg["_root"]) / "web" / "data" / "straits.json"
        if not straits_file.exists():
            return "ℹ️ Boğazlar canlı durumu şu an güncelleniyor, lütfen az sonra tekrar deneyin."
        try:
            data = json.loads(straits_file.read_text("utf-8") or "{}")
            lines = ["🚢 <b>TÜRK BOĞAZLARI CANLI GEÇİŞ DURUMU</b>\n"]
            for st in data.get("straits", []):
                status = st.get("status", "open")
                icon = "🟢" if status == "open" else ("🟡" if status == "caution" else "🔴")
                st_name = st.get("name", "Boğaz")
                st_tr = st.get("status_tr", status)
                lines.append(f"{icon} <b>{st_name}: {st_tr}</b>")
                if st.get("reason"):
                    lines.append(f"   ⚠️ Gerekçe: <i>{st['reason']}</i>")
                active = st.get("active_vessels_in_transit")
                speed = st.get("avg_speed_kn")
                if active is not None and speed is not None:
                    lines.append(f"   • Koridordaki Gemi: {active} adet | Ort. Hız: {speed:.1f} kn")
                lines.append("")
            lines.append("📞 <i>Telsiz: İstanbul VTS Ch 11/12/13/14 · Çanakkale VTS Ch 71/72/73/74</i>")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ Boğaz bilgisi okunamadı: {e}"

    def _fisherman_text(self, area_arg: str | None, s: dict) -> str:
        target_area = None
        if area_arg:
            target_area = self._match_area(area_arg)
        if not target_area and s.get("areas"):
            target_area = s["areas"][0]
        if not target_area:
            target_area = "Marmara Denizi"

        boat = s.get("boat", "small")
        if boat not in ("small", "medium", "large"):
            boat = "small"

        root = Path(self.cfg["_root"])
        outlook_file = root / "web" / "data" / "outlook.json"
        today_block = ""
        if not outlook_file.exists():
            today_block = (
                f"ℹ️ <b>{html.escape(target_area)}</b> — Bugünün çıkış penceresi henüz derlenmedi. "
                f"Bir sonraki güncelleme döngüsünü bekleyin."
            )
        else:
            try:
                data = json.loads(outlook_file.read_text("utf-8") or "{}")
                stale = _stale_banner(self.cfg, data.get("generated"))
                block = (data.get("classes") or {}).get(boat) or {}
                label = html.escape(block.get("label") or boat)
                areas = block.get("areas") or []
                missing = (data.get("coverage") or {}).get("missing") or []
                rating = next((a for a in areas if a.get("name") == target_area), None)
                if not rating:
                    miss_note = ""
                    if target_area in missing:
                        miss_note = " (bu cycle’da tahmin gelmedi)"
                    today_block = (
                        f"{stale}ℹ️ {html.escape(target_area)} için bugünün penceresi "
                        f"bulunamadı{miss_note}."
                    )
                else:
                    level_tr = {
                        "ok": "Uygun", "watch": "Dikkat",
                        "danger": "Çıkma", "unknown": "Ölçüm yok",
                    }
                    level_icon = {
                        "ok": "🟢", "watch": "🟡",
                        "danger": "🔴", "unknown": "⚪",
                    }
                    lines = [
                        f"{stale}🎣 <b>{html.escape(target_area)} · Bugün</b>",
                        f"<i>{label}</i>",
                        "",
                    ]
                    for w in rating.get("windows") or []:
                        lv = w.get("level") or "ok"
                        if lv == "ok" and self._window_hours(w) < 3:
                            continue
                        icon = level_icon.get(lv, "⚪")
                        start = html.escape(str(w.get("start") or "?"))
                        end = html.escape(str(w.get("end") or "?"))
                        gust = w.get("gust_kn")
                        wave = w.get("wave_m")
                        bits = []
                        if gust is not None:
                            bits.append(f"{gust:.0f} kn")
                        if wave is not None:
                            bits.append(f"{wave:.1f} m")
                        extra = (" · " + " · ".join(bits)) if bits else ""
                        lines.append(
                            f"{icon} <code>{start}–{end}</code>  "
                            f"{html.escape(level_tr.get(lv, lv))}{extra}"
                        )
                    rb = rating.get("return_by")
                    if rb:
                        lines.append("")
                        lines.append(f"💡 Limana dönüş: en geç <b>{html.escape(str(rb))}</b>")
                    for title in _official_warnings_for_area(root, target_area):
                        lines.append(f"📢 <b>Resmi:</b> {html.escape(title)}")
                    today_block = "\n".join(lines)
            except Exception as e:
                print(f"[bot] outlook parse error: {e}")
                today_block = "⚠️ Bugünün penceresi okunamadı."

        now_block = ""
        safety_file = root / "web" / "data" / "safety_index.json"
        if safety_file.exists():
            try:
                data = json.loads(safety_file.read_text("utf-8") or "{}")
                rating = next((r for r in data.get("ratings", []) if r.get("area") == target_area), None)
                if rating:
                    score = rating.get("score")
                    status = rating.get("status") or ""
                    quality = rating.get("data_quality") or "ok"
                    if score is None or quality == "unknown" or status == "unknown":
                        now_block = (
                            "\n\n——— <b>Şimdi</b> (anlık skor) ———\n"
                            "⚪ Veri yok / ölçüm eksik"
                        )
                    else:
                        icon = "🟢" if status == "good" else ("🟡" if status == "caution" else "🔴")
                        status_tr = (
                            "Elverişli" if status == "good"
                            else ("Tedbirli" if status == "caution" else "Elverişsiz")
                        )
                        wave = rating.get("wave_m")
                        wave_str = f"{wave:.1f} m" if wave is not None else "—"
                        wind = rating.get("wind_kn")
                        gust = rating.get("gust_kn")
                        wind_bits = []
                        if wind is not None:
                            wind_bits.append(f"{wind:.0f} kn")
                        if gust is not None:
                            wind_bits.append(f"hamle {gust:.0f} kn")
                        wind_str = " · ".join(wind_bits) if wind_bits else "—"
                        qnote = " · ölçüm eksik" if quality == "partial" else ""
                        now_block = (
                            f"\n\n——— <b>Şimdi</b> (anlık skor) ———\n"
                            f"{icon} {status_tr} · <b>{score}/100</b>{qnote}\n"
                            f"🌊 Dalga: <b>{wave_str}</b> · 💨 {wind_str}"
                        )
            except Exception as e:
                print(f"[bot] safety parse error: {e}")

        return (
            f"{today_block}{now_block}\n\n"
            f"⚠️ <i>Model tahminidir. Karar senindir; 158 / MGM teyidi alın.</i>"
        )

    @staticmethod
    def _window_hours(w: dict) -> int:
        try:
            a, b = str(w.get("start", "0:0")).split(":")
            c, d = str(w.get("end", "0:0")).split(":")
            return (int(c) * 60 + int(d) - int(a) * 60 - int(b)) // 60
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def normalize_incidents(data) -> list:
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            items = data.get("incidents")
            if isinstance(items, list):
                return items
        return []

    def _incidents_text(self) -> str:
        inc_file = Path(self.cfg["_root"]) / "web" / "data" / "incidents.json"
        if not inc_file.exists():
            return "ℹ️ Güncel kaza kaydı bulunamadı."
        try:
            data = json.loads(inc_file.read_text("utf-8") or "null")
            items = self.normalize_incidents(data)
            wanted = {"confirmed", "probable"}
            items = [i for i in items if (i.get("status") or "") in wanted]
            if not items:
                return "🌊 Türkiye karasularında şu an aktif kaza veya batma ihbarı bulunmuyor."
            lines = ["🚨 <b>TÜRKİYE KARASULARINDA GÜNCEL DENİZ OLAYLARI</b>\n"]
            for inc in items[:5]:
                typ = inc.get("type", "unknown")
                typ_tr = inc.get("type_tr") or typ
                area = inc.get("area") or "Türkiye Karasuları"
                status = inc.get("status", "signal")
                badge = "🚨 Doğrulandı" if status == "confirmed" else ("🟡 Olası" if status == "probable" else "Sinyal")
                v_name = (inc.get("vessel") or {}).get("name") or "Deniz Aracı"
                lat = inc.get("lat")
                lon = inc.get("lon")
                coords = f"({lat:.2f}°K, {lon:.2f}°D)" if lat and lon else ""
                summary = inc.get("summary") or ""
                lines.append(
                    f"• <b>{html.escape(str(typ_tr).title())}</b> — {badge}\n"
                    f"  📍 {html.escape(str(area))} {coords}\n"
                    f"  🚢 Gemi: {html.escape(str(v_name))}"
                )
                if summary:
                    lines.append(f"  ℹ️ {html.escape(str(summary)[:100])}...")
                lines.append("")
            lines.append("📞 <i>İhbar ve Acil Yardım: 158 Sahil Güvenlik · 151 Kıyı Emniyeti</i>")
            return "\n".join(lines)
        except Exception:
            return "⚠️ Olaylar okunamadı."

    # ---- command handling ----------------------------------------------------
    def handle(self, update: dict, dry: bool = True) -> None:
        msg = update.get("message") or {}
        cb = update.get("callback_query")
        if cb:
            return self._on_callback(cb, dry)
        chat = (msg.get("chat") or {}).get("id")
        if not chat:
            return
        s = self.subs.get(chat)

        # 1. Location payload check
        location = msg.get("location")
        if location and isinstance(location, dict):
            msg_date = msg.get("date")
            if msg_date is not None:
                try:
                    if (time.time() - float(msg_date)) > 900:
                        self.send(chat, "⚠️ Konumunuz güncel değil, lütfen canlı konum paylaşın.", dry=dry)
                        self.subs.save()
                        return
                except (ValueError, TypeError):
                    pass
            lat = location.get("latitude")
            lon = location.get("longitude")
            self._handle_location(chat, lat, lon, dry=dry)
            self.subs.save()
            return

        text = (msg.get("text") or "").strip()
        if not text:
            return
        low_text = _norm(text)
        aliased = _keyboard_command(text)
        if aliased:
            cmd = aliased
            text = "/" + aliased
            low_text = aliased
        else:
            cmd = low_text.split()[0].lstrip("/").split("@")[0]

        if cmd in ("start", "basla"):
            s["active"] = True
            self.send(chat, WELCOME, markup=_reply_keyboard(), dry=dry)
            self.send(chat, "👇 Hızlı menü:", markup=_inline_home_menu(), dry=dry)
        elif cmd in ("yardim", "help", "yardım", "menu", "menü"):
            self.send(chat, HELP, markup=_inline_home_menu(), dry=dry)
            # Re-attach bottom keyboard if user hid it
            self.send(chat, "⌨️ Alt menü yenilendi.", markup=_reply_keyboard(), dry=dry)
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
        elif cmd in ("neredeyim", "konum", "whereami", "pos"):
            msg_date = msg.get("date")
            if msg_date is not None:
                try:
                    if (time.time() - float(msg_date)) > 900:
                        self.send(chat, "⚠️ Konumunuz güncel değil, lütfen canlı konum paylaşın.", dry=dry)
                        self.subs.save()
                        return
                except (ValueError, TypeError):
                    pass
            parts = text.split()
            if len(parts) >= 3:
                try:
                    lat_val = float(parts[1].replace(",", "."))
                    lon_val = float(parts[2].replace(",", "."))
                    self._handle_location(chat, lat_val, lon_val, dry=dry)
                except ValueError:
                    self.send(chat, "❌ Geçersiz koordinat formatı. Örnek: <code>/neredeyim 38.3245 26.3012</code>", dry=dry)
            else:
                self.send(chat, "📍 Konumunuzu öğrenmek için lütfen Telegram'dan konumunuzu paylaşın veya koordinat girin.\nÖrnek: <code>/neredeyim 38.3245 26.3012</code>", dry=dry)
        elif cmd in ("mayday", "acil", "imdat", "sos"):
            self.send(chat, self._mayday_text(s), dry=dry)
        elif cmd in ("bogaz", "boğaz", "bogazlar", "boğazlar", "straits"):
            self.send(chat, self._straits_text(), dry=dry)
        elif cmd in ("balikci", "balıkçı", "sefer", "cikalimmi", "çıkalım"):
            parts = text.split(None, 1)
            arg = parts[1].strip() if len(parts) > 1 else None
            self.send(chat, self._fisherman_text(arg, s), dry=dry)
        elif cmd in ("kazalar", "kaza", "batanlar", "olaylar", "sonolaylar"):
            self.send(chat, self._incidents_text(), dry=dry)
        elif cmd in ("abone", "subscribe"):
            parts = text.split(None, 1)
            if len(parts) < 2:
                areas_list = ", ".join(self.areas)
                self.send(chat, f"ℹ️ Lütfen abone olmak istediğiniz bölgeyi belirtin.\nÖrnek: <code>/abone Marmara Denizi</code>\n\nGeçerli bölgeler:\n{areas_list}\n\nİptal için: /abone iptal", dry=dry)
            else:
                sub_arg = parts[1].strip()
                norm_arg = _norm(sub_arg)
                if norm_arg in ("iptal", "cancel", "kapat", "stop", "cikis"):
                    s["areas"] = []
                    s["active"] = False
                    self.send(chat, "🔕 Aboneliğiniz iptal edildi. Tekrar açmak için: /start veya /abone [bölge]", dry=dry)
                else:
                    matched = self._match_area(sub_arg)
                    if matched:
                        s["active"] = True
                        if "areas" not in s or not isinstance(s["areas"], list):
                            s["areas"] = []
                        if matched not in s["areas"]:
                            s["areas"].append(matched)
                        self.send(chat, f"✅ <b>{matched}</b> bölgesine başarıyla abone oldunuz.\n\nAboneliği iptal etmek için: /abone iptal", dry=dry)
                    else:
                        areas_list = ", ".join(self.areas)
                        self.send(chat, f'❌ Geçersiz bölge adı: "{sub_arg}"\n\n'
                                        f"Lütfen geçerli bir bölge adı girin: {areas_list}\n\n"
                                        f"Aboneliği sonlandırmak için: /abone iptal", dry=dry)
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
        elif data.startswith("menu:"):
            action = data.split(":", 1)[1]
            note = action
            if action == "balikci":
                self.send(chat, self._fisherman_text(None, s), dry=dry)
            elif action == "durum":
                self.send_outlook_now(chat, s, dry=dry)
            elif action == "bogaz":
                self.send(chat, self._straits_text(), dry=dry)
            elif action == "kazalar":
                self.send(chat, self._incidents_text(), dry=dry)
            elif action == "neredeyim":
                self.send(chat, "📍 Konumunu Telegram’dan paylaş veya yaz:\n<code>/neredeyim 40.98 28.85</code>", dry=dry)
            elif action == "mayday":
                self.send(chat, self._mayday_text(s), dry=dry)
            elif action == "bolge":
                self.send(chat, "🌊 <b>Hangi denizleri takip ediyorsun?</b>",
                          self._area_markup(s.get("areas", [])), dry=dry)
            elif action == "tekne":
                self.send(chat, "⛵ <b>Tekne boyun?</b>",
                          self._boat_markup(s.get("boat", "small")), dry=dry)
            elif action == "ayarlar":
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
    def poll(self, dry: bool = True, limit: int = 50, timeout: int = 20) -> int:
        """Drain pending updates. Offset is persisted so a restart does not
        replay yesterday's commands. Uses Telegram long-polling (timeout>0)
        to drastically reduce battery drain and HTTP handshakes."""
        if not self.token:
            return 0
        if not self._commands_registered and not dry:
            try:
                self.register_commands()
                self._commands_registered = True
            except Exception:
                pass
        res = self._api("getUpdates", {"offset": self.subs.offset + 1,
                                       "limit": limit, "timeout": timeout},
                        timeout=timeout + 10)
        if not res:
            return 0
        for up in res:
            self.subs.offset = max(self.subs.offset, int(up.get("update_id", 0)))
            try:
                self.handle(up, dry=dry)
            except Exception as e:
                try:
                    print(f"[bot] update islenemedi: {e}")
                except UnicodeEncodeError:
                    print(f"[bot] update islenemedi: {repr(e)}")
        self.subs.save()
        return len(res)
