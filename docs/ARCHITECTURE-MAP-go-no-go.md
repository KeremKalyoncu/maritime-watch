# Mimari Uyum ve Dosya Haritası — Go / No-Go Window Alignment

| Alan | Değer |
|------|--------|
| **Özellik** | `outlook-cache-surfaces` (bkz. `FEATURE-go-no-go-alignment.md`) |
| **Hedef** | Mevcut pipeline’a uyumlu entegrasyon; yeni framework / katman icat etmeden |
| **İlgili Context** | `docs/FEATURE-go-no-go-alignment.md` |

---

## Proje detayları / teknoloji yığını (doldurulmuş)

Maritime Watch, klasik “Controllers / Services / Repositories” isimlendirmesi kullanmaz. Katmanlar **pipeline odaklı modüler monolit**tir:

| Katman (proje dili) | Klasik karşılık | Konum |
|---------------------|-----------------|--------|
| Orchestrator | Application entry / use-case runner | `run.py` |
| Config | Settings | `config.yaml`, `src/config.py`, `.env` |
| Ingest | Adapters / gateways (dış API) | `src/ingest/*` |
| Process | Domain services | `src/process/*` |
| Model + Store | Entities + persistence | `src/model.py`, `src/store.py`, `data/*`, `web/data/*` |
| Render | Presenters / static API | `src/render/*` → `web/data/*.json` |
| Alert | Notification adapters | `src/alert/telegram.py`, `src/alert/bot.py` |
| Web UI | Presentation (vanilla) | `web/index.html`, `web/app.js`, `web/style.css` |
| Tests / Eval | QA | `tests/`, `eval/` |
| CI | Scheduled worker + Pages | `.github/workflows/update.yml` |

**Stack:** Python 3.11–3.13 · `requests`, `beautifulsoup4`, `websockets`, `PyYAML`, `python-dotenv` · stdlib HTTP server · vanilla JS + Leaflet CDN · JSON file store · GitHub Actions + Pages · edge bot host (Termux / Note 4).

**Veri sözleşmesi:** Cycle üretir → `web/data/*.json` → tarayıcı ve bot **aynı dosyaları** okur. DB yok.

---

## 1. Etkilenecek dosyalar

Katman adları proje jargonunda; yanlarında Clean Architecture benzeri rol notu.

### 1.1 Orchestrator (Application)

| Dosya | Rol | Değişiklik |
|-------|-----|------------|
| `run.py` | Cycle orkestrasyonu | `render_outlook(...)` çağrısı ekle (safety_index / weather_grid yanına). `send_daily_outlook` mümkünse cache’li metin yoluna dokunsun veya mevcut kalsın (minimal diff). |

### 1.2 Domain / Process (Services)

| Dosya | Rol | Değişiklik |
|-------|-----|------------|
| `src/process/window.py` | Go/No-Go domain motoru | **Çekirdek dokunulmaz** veya ince yardımcı: örn. `return_by_hhmm(area) -> str \| None` (first danger/watch sınırı). Mevcut `build` / `AreaOutlook` / `Window` aynen kullanılır. |
| `src/process/safety_index.py` | Anlık skor servisi | Null dalga/SST’te kör “good/100” bastırmama; öneri metninde “anlık · küçük tekne varsayılan” netliği. İsteğe bağlı: sınıf limitlerini config’ten okuma (hafif). |
| `src/process/cpa.py` | CPA domain | `detect_cpa_risks`: MMSI dedupe + `mmsi1 == mmsi2` skip. |

### 1.3 Render / Presenters (yeni + mevcut)

| Dosya | Rol | Değişiklik |
|-------|-----|------------|
| **`src/render/outlook.py`** *(YENİ)* | Outlook presenter | `fetch_forecast_points` + `window.build` × `outlook.classes` → `web/data/outlook.json`. Şema: `generated`, `hours`, `tz_offset_hours`, `classes: { small: { label, limits, areas: [...] } }`. |
| `src/render/weather_grid.py` | Hava grid | Dokunulmaz (gerekmez); outlook kendi Open-Meteo noktalarını kullanır (zaten cache’li `openmeteo`). |
| `src/render/mapdata.py` / `health.py` | Özet / health | İsteğe bağlı: health’e `outlook` ok bayrağı — **zorunlu değil**, scope şişmesin. |

### 1.4 Alert adapters (Bot / Notifier)

| Dosya | Rol | Değişiklik |
|-------|-----|------------|
| `src/alert/bot.py` | Telegram command controller | `_fisherman_text` → `outlook.json` + sınıf (`sub.boat`); skor ikinci blok. `_incidents_text` → list *veya* `{incidents}`. Help metnini güncelle. |
| `src/alert/telegram.py` | Mesaj formatı | `outlook_text`: “Limana dönüş en geç HH:MM”. `outlook_text_for`: önce disk cache; yoksa nazik boş/“veri yok” (**production’da canlı fetch yok** — Feature Out of Scope). |

### 1.5 Ingest (Repositories / Gateways)

| Dosya | Rol | Değişiklik |
|-------|-----|------------|
| `src/ingest/openmeteo.py` | Forecast gateway | Tercihen **dokunulmaz**. Mevcut `fetch_forecast_points` + in-cycle cache yeterli. Yeni paket yok. |

### 1.6 Config / Model

| Dosya | Rol | Değişiklik |
|-------|-----|------------|
| `config.yaml` | Davranış | İsteğe bağlı `outlook.web_default_class: small`. Mevcut `classes` / `hours` / `tz_offset_hours` yeterli. |
| `src/model.py` | Entity | **Gerekmez** (JSON dict yeterli). İleride dataclass eklenecekse ayrı PR. |
| `.gitignore` | Artifact politikası | `web/data/outlook.json` — diğer generated gibi ignore *veya* seed için commit; mevcut `safety_index` politikasıyla **aynı kural** (şu an ignore listesinde). Ignore’a ekle. |

### 1.7 Web UI (Components — vanilla)

| Dosya | Rol | Değişiklik |
|-------|-----|------------|
| `web/index.html` | Shell | “Bugün çıkılır mı?” paneli: bölge + tekne sınıfı select; `#outlook-panel` mount noktası (`safety-strip` altı veya üstü). |
| `web/app.js` | UI logic | `getJSON("data/outlook.json")`; panel render; TR/EN kısa etiketler; mevcut safety strip’i “Şimdi” diye etiketle. |
| `web/style.css` | Stil | İnce şerit / timeline (yeşil-sarı-kırmızı); mevcut CSS değişkenlerine uy. Kart/dashboard şişirmesi yok. |
| `web/sw.js` | PWA cache | `outlook.json` için diğer `data/*.json` ile aynı network-first davranış (gerekirse glob zaten `/data/` kapsıyorsa **dokunma**). |

### 1.8 Tests

| Dosya | Rol | Değişiklik |
|-------|-----|------------|
| `tests/test_outlook.py` | Domain / mesaj | Return-by satırı; cache şeması smoke. |
| `tests/test_bot.py` | Bot | `/balikci` pencere; `/kazalar` dizi fixtures. |
| `tests/test_cpa.py` | CPA | Self-MMSI + duplicate MMSI. |
| `tests/test_safety_index.py` | Skor | Null ölçüm güveni. |
| **`tests/test_render_outlook.py`** *(YENİ, ince)* | Presenter | tmp_path’e JSON yazar; 3 sınıf anahtarı. |

### 1.9 Docs (bu feature setinin parçası)

| Dosya | Rol | Değişiklik |
|-------|-----|------------|
| `docs/FEATURE-go-no-go-alignment.md` | Context | Zaten var — uygulama sonrası DoD tick. |
| `docs/ARCHITECTURE-MAP-go-no-go.md` | Bu dosya | Mapping kilidi. |
| `README.md` | Kullanıcı vaadi | `/balikci` + web pencere; drift düzeltmesi (kısa). |
| `TODO.md` | Roadmap | İlgili maddeleri Done’a çek / yanlış Next’i düzelt. |
| `ARCHITECTURE.md` | Pipeline diyagramı | `outlook.json` kutusunu bir satır ekle (commit 2 chore). |

### 1.10 Bilerek dokunulmayan

`src/sdr/*` · `src/ingest/navwarn.py` / `reliefweb.py` (kapalı) · `eval/*` (zorunlu değil) · parent `proje 1/*.md` pazarlama · yeni npm/React.

### 1.11 Dosya yolu taslağı (özet ağaç)

```
maritime-watch/
├── run.py                          # + render_outlook hook
├── config.yaml                     # opsiyonel web_default_class
├── .gitignore                      # + web/data/outlook.json
├── docs/
│   ├── FEATURE-go-no-go-alignment.md
│   └── ARCHITECTURE-MAP-go-no-go.md   # bu dosya
├── src/
│   ├── process/
│   │   ├── window.py               # + return_by helper (minimal)
│   │   ├── safety_index.py         # null / etiket güveni
│   │   └── cpa.py                  # MMSI hygiene
│   ├── render/
│   │   └── outlook.py              # YENİ presenter
│   └── alert/
│       ├── bot.py                  # /balikci, /kazalar
│       └── telegram.py             # return-by + cache-first
├── web/
│   ├── index.html                  # outlook panel mount
│   ├── app.js                      # load + render outlook
│   └── style.css                   # strip styles
│   └── data/
│       └── outlook.json            # generated (gitignore)
└── tests/
    ├── test_outlook.py
    ├── test_bot.py
    ├── test_cpa.py
    ├── test_safety_index.py
    └── test_render_outlook.py      # YENİ
```

---

## 2. Tasarım kalıbı — mevcut mimariye uyum ilkeleri

Proje **Clean Architecture isimlendirmesi taşımaz**; fiilen şu desene uyar:

> **Ingest → Process → Store → Render → Alert** + statik JSON sözleşmesi.

Bu feature için izlenecek prensipler:

### 2.1 Tek yönlü bağımlılık

- `render/outlook.py` → `process/window` + `ingest/openmeteo` (ok).  
- `alert/bot.py` → **yalnızca** `web/data/outlook.json` (ve mevcut safety/incidents). Bot, `window.build` veya Open-Meteo import etmez (Note 4 / katman sınırı).  
- `web/app.js` → yalnızca HTTP JSON; Python bilmez.

### 2.2 “Rules, not frameworks”

- Yeni servis bus, DI container, plugin API yok.  
- Presenter = saf fonksiyon + dosyaya yaz (örnek: `render_straits_status`, `render_safety_index`).

### 2.3 Domain tek kaynak (DRY)

- Saat penceresi matematiği **sadece** `window.py`.  
- Telegram metin formatı `telegram.outlook_text`; bot `/balikci` aynı domain çıktısını (JSON’daki pencereler) insan diline çevirir — ikinci bir eşik tablosu yazılmaz.

### 2.4 İki kavram, iki artifact

| Artifact | Soru | Etiket |
|----------|------|--------|
| `outlook.json` | Bugün, saat kaça kadar? | **Bugün** |
| `safety_index.json` | Şu an nasıl? | **Şimdi** |

UI/bot kopyası bu ayrımı bozmaz; skor “Go/No-Go’nun yerine” geçmez.

### 2.5 Zero-ops persistence

- Yeni tablo yok; Pages’in zaten dağıttığı `web/data` sözleşmesine bir dosya eklenir.  
- CI temiz checkout: `outlook.json` regenerate edilir (gitignore ile uyumlu).

### 2.6 Fail-soft

- Outlook render hata verirse cycle diğer render’ları durdurmaz (`try/except` + log) — `run.py`’deki safety_index/straits kalıbı.  
- Bot dosya yoksa: “henüz derlenmedi”, uydurma pencere yok (fixture sızıntısı dersi).

### 2.7 Test edilebilirlik

- Presenter tmp_path ile birim test.  
- Bot testleri fixture JSON ile (ağ yok).  
- CPA hygiene saf fonksiyon seviyesinde.

### 2.8 Edge host sözleşmesi

- Ağır iş: Actions `run.py --once`.  
- Note 4: `Bot.poll` + dosya okuma. Bu feature Note 4’e yeni daemon / ek ingest eklemez.

---

## 3. Bağımlılıklar

### 3.1 Mevcut runtime (`requirements.txt`) — **yeni paket yok**

| Paket | Min | Bu feature’da kullanım | Uyumluluk notu |
|-------|-----|------------------------|----------------|
| `requests` | ≥2.31 | Open-Meteo (mevcut ingest) | Değişmez; outlook presenter mevcut fetch’i çağırır |
| `beautifulsoup4` | ≥4.12 | Kullanılmaz (bu feature) | — |
| `websockets` | ≥12.0 | Kullanılmaz (bu feature) | AIS burst ayrı; CPA hygiene AIS çıktısına dokunur, yeni WS yok |
| `PyYAML` | ≥6.0 | `config.yaml` classes | Değişmez |
| `python-dotenv` | ≥1.0 | Bot token (mevcut) | Değişmez |

**Stdlib:** `json`, `pathlib`, `time`, `html` (telegram escape) — yeterli.

### 3.2 Frontend — **yeni npm / bundler yok**

| Kaynak | Not |
|--------|-----|
| Leaflet 1.9.x (CDN) | Mevcut; outlook paneli harita dışı DOM |
| Vanilla JS | `fetch` / mevcut `getJSON` |

### 3.3 Test / CI

| Araç | Not |
|------|-----|
| `pytest` | Dev/CI; yeni paket gerekmez (workflow’da zaten) |
| `ruff` | Lint; API değişimi yok |

### 3.4 Bilinçli olarak eklenmeyecekler

- Redis, SQLite, SQLAlchemy  
- httpx / aiohttp (mevcut `requests` yeter)  
- pydantic / attrs (JSON dict + mevcut dataclass’lar yeter)  
- React, Vite, Tailwind  
- pandas / numpy (pencere motoru saf Python)

### 3.5 Versiyon / ortam uyumu

| Ortam | Beklenti |
|-------|----------|
| CI Python 3.11–3.13 | `outlook.py` 3.11+ type hint (`str \| None`) mevcut stil |
| Note 4 Termux Python | Bot yalnızca JSON okur → 3.10+ yeterli; yeni C-extension yok |
| GitHub Pages | Statik `outlook.json`; content-type JSON |

### 3.6 Operasyonel bağımlılık (kod dışı)

| Bağımlılık | Rol |
|------------|-----|
| Open-Meteo API | Cycle ingest (mevcut); feature yeni kota modeli icat etmez |
| GitHub Actions cron | `outlook.json` üretimi |
| Note 4 SSH (`ssh note4`) | `git pull` + bot restart; ingest taşıma yok |

---

## Entegrasyon sırası (uygulama için kısa checklist)

1. `src/render/outlook.py` + `run.py` hook + `.gitignore`  
2. `window` return-by + `telegram.outlook_text`  
3. `bot._fisherman_text` / `_incidents_text`  
4. `cpa` + `safety_index` hygiene  
5. `web/*` panel  
6. Testler  
7. README/TODO drift (commit 2)

Bu sıra, katman ihlali olmadan (önce artifact, sonra tüketiciler) ilerler.

---

*Mapping kilidi: yeni katman adı uydurulmaz; mevcut `render/` + JSON sözleşme genişletilir.*
