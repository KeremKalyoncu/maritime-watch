# Uygulama Görev Listesi — Go / No-Go Window Alignment

| Alan | Değer |
|------|--------|
| **Özellik** | `outlook-cache-surfaces` |
| **Kaynak planlar** | Feature · Architecture · Data Model · API · Business Logic · UI/UX · NFR |
| **Commit hedefi** | 2 commit (tüm maddeler bitince; ara WIP push yok) |
| **Host** | Ağır iş Actions · Note 4 yalnız bot okuma |

---

## Uygulanacak özellik özeti

Küçük tekne sahibine verilen asıl cevap (**bugün çıkabilir miyim, saat kaça kadar?**) web + `/balikci` + sabah outlook’ta aynı dilde olsun. Cycle’da `window.py` ile 3 tekne sınıfı hesaplanır → `web/data/outlook.json` → bot/web dosyadan okur (Note 4’te Open-Meteo yok). Skor = **Şimdi** (ikincil). Ek: `return_by`, `/kazalar` JSON toleransı, CPA MMSI hygiene, safety null güveni, fail-soft + escape. Yeni paket/DB/Redis/SDR yok.

---

## Nasıl kullanılır?

1. Sırayı bozma (aşağıdaki faz sırası = DB→Model→Servis→API→UI eşlemesi).  
2. Her `[ ]` tek amaç; bitince yanındaki **Doğrulama**’yı çalıştır.  
3. **DURAKLAMA** satırında dur: test yeşil değilse sonraki faza geçme.  
4. Agent context dolarsa: “Faz N, madde X’ten devam” diye resume et.

**Katman eşlemesi (SQL yok):**

| Klasik sıra | Bu projede |
|-------------|------------|
| DB | JSON şema + `.gitignore` + atomic write |
| Model/Type | `window` türevleri + TypedDict/serileştirme |
| Servis/İş mantığı | `render/outlook.py`, CPA, safety, return_by |
| API | Cycle hook + bot okuma sözleşmesi (Static GET) |
| UI | `#outlook-panel` + i18n |

---

## Faz 0 — Hazırlık (dokunmadan kilitle)

- [ ] **0.1** Plan dosyalarının yerinde olduğunu doğrula: `docs/FEATURE-*.md`, `ARCHITECTURE-MAP-*`, `DATA-MODEL-*`, `API-CONTRACT-*`, `BUSINESS-LOGIC-*`, `UI-UX-*`, `NFR-*`
- [ ] **0.2** `pytest -q` (veya mevcut test komutu) baseline yeşil mi bak; kırmızı varsa önce not et
- [ ] **0.3** Branch: yerel çalış; force-push yok

**Doğrulama 0:** Baseline test sonucu not edildi.

### DURAKLAMA 0
`ONAY: baseline OK — Faz 1'e geç`

---

## Faz 1 — “DB” / kalıcılık sözleşmesi

- [ ] **1.1** `.gitignore` içine `web/data/outlook.json` ekle (`safety_index.json` ile aynı politika)
- [ ] **1.2** (Opsiyonel) `config.yaml` → `outlook.web_default_class: small` ekle; yoksa default kodda `small`
- [ ] **1.3** `DATA-MODEL` şemasını referans alarak örnek fixture yaz: `tests/fixtures/outlook_sample.json` (küçük, 1–2 area, 3 class iskeleti)

**Doğrulama 1:**
```text
- git check-ignore web/data/outlook.json  → ignored
- fixture JSON elle okunabilir; schema_version: 1
```

### DURAKLAMA 1
`ONAY: kalıcılık sözleşmesi hazır — Faz 2'ye geç`

---

## Faz 2 — Model / type / domain türevleri

- [ ] **2.1** `src/process/window.py`: `return_by(area: AreaOutlook) -> str | None` (danger.start → watch.start → None) saf fonksiyon
- [ ] **2.2** `AreaOutlook` serileştirme yardımcısı: `to_public_dict()` veya `render` içinde eşdeğer — alanlar: name, lat, lon, windows[], max_gust, max_wave, first_danger_start, return_by, worst
- [ ] **2.3** `Window` → `{start,end,level,gust_kn,wave_m}` dict
- [ ] **2.4** `tests/test_outlook.py`: return_by üç senaryo (danger / yalnız watch / hep ok)

**Doğrulama 2:**
```bash
pytest tests/test_outlook.py -q
```

### DURAKLAMA 2
`ONAY: domain return_by + serileştirme yeşil — Faz 3'e geç`

---

## Faz 3 — Servis / iş mantığı (render + yan düzeltmeler)

### 3.A Outlook presenter

- [ ] **3.1** Yeni `src/render/outlook.py` oluştur: `render_outlook(cfg, out_file) -> dict`
- [ ] **3.2** İçeride `fetch_forecast_points` + her `outlook.classes` için `window.build`
- [ ] **3.3** Çıktı `OutlookFile` şekli: schema_version, generated, hours, tz_offset_hours, question="today", classes
- [ ] **3.4** Live nokta yok / sample → yazma (BUSINESS-LOGIC V6); WARN log
- [ ] **3.5** Atomic write: `.tmp` + `Path.replace`
- [ ] **3.6** `tests/test_render_outlook.py`: tmp_path, monkeypatch live points, 3 class key assert, boyutu &lt; 256KB

### 3.B CPA hygiene

- [ ] **3.7** `detect_cpa_risks`: MMSI dedupe (son konum), `mmsi1 == mmsi2` skip
- [ ] **3.8** `tests/test_cpa.py`: self-pair ve duplicate MMSI

### 3.C Safety null güveni

- [ ] **3.9** `safety_index`: `data_quality`, `baseline_boat_class`, unknown iken kör good/100 engeli
- [ ] **3.10** `tests/test_safety_index.py`: null wave+sst

**Doğrulama 3:**
```bash
pytest tests/test_render_outlook.py tests/test_cpa.py tests/test_safety_index.py tests/test_outlook.py -q
```

### DURAKLAMA 3
`ONAY: servis katmanı yeşil — Faz 4'e geç`

---

## Faz 4 — API / entegrasyon (orchestrator + bot sözleşmesi)

### 4.A Cycle hook

- [ ] **4.1** `run.py`: `render_outlook` çağrısı (weather_grid / safety yakınında), `try/except` fail-soft, `[outlook]` log
- [ ] **4.2** Dry-run: `py run.py --once --no-ais` (ağ varsa) veya test mock ile dosya üretildiğini doğrula

### 4.B Telegram metin

- [ ] **4.3** `telegram.outlook_text`: `return_by` satırı (html.escape)
- [ ] **4.4** `outlook_text_for`: production path **önce** `web/data/outlook.json` oku; yoksa “veri yok” (Open-Meteo çağırma — NFR)
- [ ] **4.5** Mevcut outlook testlerini güncelle / kırılan assert’leri düzelt

### 4.C Bot komutları

- [ ] **4.6** `_fisherman_text`: Bugün = outlook windows + return_by; Şimdi = safety ikinci blok; escape
- [ ] **4.7** `_incidents_text`: `normalize_incidents()` — list veya `{incidents:[]}`; filter confirmed+probable; limit 5
- [ ] **4.8** Help metni `/balikci` açıklamasını saat penceresine çevir
- [ ] **4.9** `tests/test_bot.py`: fixture outlook + incidents array; `/balikci` saat içerir; `/kazalar` boş değil (confirmed fixture)

**Doğrulama 4:**
```bash
pytest tests/test_bot.py tests/test_outlook.py tests/test_telegram.py -q
# test_telegram yoksa ilgili mevcut dosyalar
ruff check src/render/outlook.py src/alert/bot.py src/alert/telegram.py src/process/cpa.py src/process/safety_index.py run.py
```

### DURAKLAMA 4
`ONAY: API/bot sözleşmesi yeşil — Faz 5'e geç`

---

## Faz 5 — UI

- [ ] **5.1** `index.html`: `#outlook-panel` mount (`#safety-strip` sonrası)
- [ ] **5.2** `style.css`: `.outlook-panel`, segment renkleri, mobil wrap/scroll — kart şişirmesi yok
- [ ] **5.3** `app.js` i18n key’leri (TR/EN)
- [ ] **5.4** Dumb helpers: controls, timeline, returnBy, now, status
- [ ] **5.5** Smart: `LAST.outlook` load (diğer `getJSON` ile paralel), panel state `{boat, area}`, render
- [ ] **5.6** State’ler: loading skeleton · success · empty · error (UI-UX tablosu)
- [ ] **5.7** Warm refresh: 60s reload içeriği silmeden swap
- [ ] **5.8** XSS: dinamik metin `textContent` veya escape; `innerHTML` yalnız sabit iskelet
- [ ] **5.9** Safety strip / skor dilini “Şimdi” ile etiketle (karışıklık olmasın)

**Doğrulama 5:**
```text
- py run.py --serve  (veya fixture'ı web/data'ya kopyala)
- Tarayıcı: panel görünür; boat/area değişince timeline değişir; network'te select başına yeni GET yok
- outlook yokken error/empty copy
- mobil genişlik ~390px kontrol
```

### DURAKLAMA 5
`ONAY: UI manuel OK — Faz 6'ya geç`

---

## Faz 6 — NFR sertleştirme + doküman drift

- [ ] **6.1** Bot modülünde `/balikci` hot path’in `openmeteo` import etmediğini grep/test ile doğrula
- [ ] **6.2** Sample refuse testi (varsa güçlendir)
- [ ] **6.3** README: `/balikci` + web pencere vaadini gerçekle hizala (kısa)
- [ ] **6.4** `TODO.md`: Kandilli/done drift; bu feature maddelerini Done’a çek
- [ ] **6.5** `ARCHITECTURE.md`: bir satır `outlook.json` kutusu
- [ ] **6.6** Feature DoD checklist’ini `FEATURE-*.md` içinde işaretle

**Doğrulama 6:**
```bash
pytest -q
ruff check src tests run.py
```

### DURAKLAMA 6
`ONAY: tam süit yeşil — Commit fazına geç`

---

## Faz 7 — Commit (az ve temiz)

> Kullanıcı açıkça istemeden push etme. Commit mesajları *why* odaklı.

- [ ] **7.1** Commit 1 — kod + test + UI + gerekli README parçası:
  ```
  fix: align go/no-go windows across bot, web, and outlook cache

  Primary surfaces answered with a safety score instead of hour
  windows; fishermen were not getting the product we advertise.
  Cache outlook.json from the cycle so the Note 4 bot never
  re-fetches Open-Meteo per command.
  ```
  Dahil: `src/render/outlook.py`, window/cpa/safety, bot/telegram, run.py, web/*, tests/*, .gitignore, kısa README

- [ ] **7.2** Commit 2 — doküman drift + temizlik:
  ```
  chore: tidy go/no-go docs drift and roadmap notes

  Keep TODO/ARCHITECTURE aligned with the outlook cache surfaces
  work without bundling more product scope.
  ```
  Dahil: TODO, ARCHITECTURE, docs DoD tick’leri, gereksiz gürültü

- [ ] **7.3** `git status` temiz; secret yok

### DURAKLAMA 7
`ONAY: commit'ler lokal OK — Note 4 / Pages deploy`

---

## Faz 8 — Deploy (prod patlamasın)

- [ ] **8.1** Push (kullanıcı onayıyla) → Actions `update-and-publish` veya cron bekle
- [ ] **8.2** `curl -sI https://keremkalyoncu.github.io/maritime-watch/data/outlook.json` → 200
- [ ] **8.3** `ssh note4` → `git pull` → bot process restart (tmux/systemd ne ise)
- [ ] **8.4** Telegram: `/balikci marmara` → saat + return_by; `/kazalar` → liste veya dürüst boş
- [ ] **8.5** Site: panel + sınıf değişimi smoke

### DURAKLAMA 8
`ONAY: prod smoke OK — özellik DONE`

---

## Context dolarsa — resume haritası

| Kaldığın yer | Devam komutu |
|--------------|--------------|
| Faz 2 ortası | “Faz 2.x’ten devam: return_by + test_outlook” |
| Faz 3A | “render/outlook.py atomic write + test_render_outlook” |
| Faz 4C | “bot _fisherman_text + _incidents_text + test_bot” |
| Faz 5 | “#outlook-panel UI states” |
| Faz 7 | “2 commit planına göre commit et, push yok” |

---

## Yapılmayacaklar (görev listesine sızmasın)

- SDR, Redis, SQL, React, yeni VPS mimarisi  
- Her atomik adımda ayrı GitHub commit  
- Parent klasör pazarlama md temizliği (ayrı iş)  
- Note 4’te ingest taşıma  

---

## İlerleme özeti (agent işaretlesin)

| Faz | Durum |
|-----|--------|
| 0 Hazırlık | [ ] |
| 1 Kalıcılık | [ ] |
| 2 Domain | [ ] |
| 3 Servis | [ ] |
| 4 API/Bot | [ ] |
| 5 UI | [ ] |
| 6 NFR/Docs | [ ] |
| 7 Commit | [ ] |
| 8 Deploy | [ ] |

---

*Atomik kural: bir checkbox = bir doğrulanabilir sonuç. DURAKLAMA = test kapısı.*
