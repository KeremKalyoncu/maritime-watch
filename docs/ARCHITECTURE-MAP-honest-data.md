# Mimari Uyum ve Dosya Haritası — Honest Data Integrity

| Alan | Değer |
|------|--------|
| **Özellik** | `honest-data-integrity` |
| **Hedef** | Mevcut pipeline monolitine cerrahi yama; yeni katman yok |
| **İlgili** | `FEATURE-honest-data.md` |

---

## Proje detayları / teknoloji yığını

Pipeline: `ingest → process → store → render → alert` · JSON sözleşme · Vanilla web · Telegram bot · Actions cycle / Note 4 poll.

---

## 1. Etkilenecek dosyalar

| Katman | Dosya | Değişiklik |
|--------|-------|------------|
| Orchestrator | `run.py` | Forecast noktalarını bir kez çek → outlook + weather_grid paylaş; outlook sırası net |
| Ingest | `src/ingest/openmeteo.py` | Partial nokta (wind-only); None hizalı seriler; `wind_direction_10m` |
| Process | `src/process/window.py` | `unknown` seviye; dürüst `level_for` |
| Render | `src/render/outlook.py` | `coverage` (expected/present/missing) |
| Render | `src/render/weather_grid.py` | Eksik fp → 0 invent etme; gerçek rüzgâr yönü |
| Alert | `src/alert/bot.py` | Sahte skor kaldır; stale; MGM satırı; unknown UI |
| Web | `web/app.js`, `web/style.css` | Stale outlook + MGM + unknown segment |
| Config | `config.yaml` | `outlook.stale_hours` (opsiyonel, default alert ile) |
| Tests | `tests/test_outlook.py`, `test_bot.py`, `test_render_outlook.py`, (+ gerekirse weather_grid) | Davranış kilitleri |
| Docs | `docs/*-honest-data.md` | Bu paket |

**Yeni paket / dependency yok.**

---

## 2. Tasarım kalıbı

1. **Tek yazım, çok okuma** — cycle üretir; bot/web sadece okur.  
2. **Fail-soft / say-nothing** — eksik veri → `unknown` veya açık mesaj; asla yeşil uydurma.  
3. **Partial coverage açıkça** — `coverage.missing[]` gizlenmez.  
4. **Mevcut motor** — `window.build` genişler; yeni pencere motoru yok.

---

## 3. Bağımlılıklar

| Paket | Not |
|-------|-----|
| `requests`, mevcut stack | Değişmez |
| Open-Meteo `wind_direction_10m` | Aynı forecast URL; ekstra servis yok |
| MGM | Mevcut `scrape_mgm_alarms` → `warnings.json` |
