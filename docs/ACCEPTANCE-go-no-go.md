# Kabul Kriterleri ve Test Senaryoları — Go / No-Go Window Alignment

| Alan | Değer |
|------|--------|
| **Özellik** | `outlook-cache-surfaces` |
| **Kaynak** | Feature · Data Model · API · Business Logic · UI/UX · NFR · Task List |
| **Test koşumu** | `pytest -q` · `ruff check` · manuel tarayıcı · Telegram · (opsiyonel) `curl` Pages |
| **Postman** | Zorunlu değil — API = Static GET; `curl` yeterli |

---

## Doğrulanacak özellik (bitmiş hâl)

1. Cycle `web/data/outlook.json` üretir (3 sınıf × bölgeler × saat pencereleri + `return_by`).  
2. Web `#outlook-panel`: bölge + tekne sınıfı → **Bugün** yeşil/sarı/kırmızı saatler + varsa “en geç HH:MM”.  
3. Altında **Şimdi** = safety skor (ikincil); skor pencerenin yerini almaz.  
4. `/balikci` aynı Bugün dilini verir; Note 4 path’inde Open-Meteo çağrılmaz.  
5. `/kazalar` top-level `incidents[]` ile çalışır (confirmed/probable).  
6. CPA self-MMSI gürültüsü yok; safety null ölçümde kör 100/good yok.  
7. Open-Meteo/sample fail → sahte pencere yok; eski artifact korunur.  
8. XSS: dinamik metin escape; secrets artifact’ta yok.

---

## 1. Unit / Integration test senaryoları

Her satır: **ID · Dosya · Senaryo · Given / When / Then**.  
`[ ]` = yazıldı ve yeşil.

### 1.1 Domain — `window` / return_by (`tests/test_outlook.py`)

| ID | Tip | Senaryo | Beklenen | Done |
|----|-----|---------|----------|------|
| U-W1 | Happy | Ardışık ok saatler | Tek `ok` penceresi, birleşik end | [ ] |
| U-W2 | Happy | danger var | `return_by == first_danger.start` | [ ] |
| U-W3 | Happy | yalnız watch, danger yok | `return_by == first_watch.start` | [ ] |
| U-W4 | Happy | hep ok | `return_by is None` | [ ] |
| U-W5 | Fail | `times=[]` | boş windows; crash yok | [ ] |
| U-W6 | Happy | `level_for` eşik | gust ≥ limit → danger; 0.75× → watch | [ ] |
| U-W7 | Happy | short sliver merge | &lt;2h ok, sert bloklar arasında yutulur | [ ] |

### 1.2 Presenter — `render_outlook` (`tests/test_render_outlook.py`)

| ID | Tip | Senaryo | Beklenen | Done |
|----|-----|---------|----------|------|
| U-R1 | Happy | 2 live point, 3 class | dosyada `classes.small\|medium\|large`; `schema_version=1`; `question=today` | [ ] |
| U-R2 | Happy | area dict alanları | windows, worst, return_by, max_gust/wave | [ ] |
| U-R3 | Fail | zero live points | **yazma yok** veya boş areas politikası (BUSINESS-LOGIC ile tutarlı); sample yok | [ ] |
| U-R4 | Fail | `SAMPLES_ALLOWED` false + sample-only fetch | outlook publish yok | [ ] |
| U-R5 | Happy | atomic write | hedef dosya geçerli JSON; yarım dosya kalmaz | [ ] |
| U-R6 | NFR | payload size | serialized &lt; 256_000 bytes | [ ] |
| U-R7 | Fail | build exception | `render_outlook` raise etmeden log (veya caller fail-soft — integration) | [ ] |

### 1.3 CPA (`tests/test_cpa.py`)

| ID | Tip | Senaryo | Beklenen | Done |
|----|-----|---------|----------|------|
| U-C1 | Happy | iki farklı MMSI yakın | event üretilebilir (mevcut eşikler) | [ ] |
| U-C2 | Fail | aynı MMSI iki satır | dedupe sonrası self-pair **0 event** | [ ] |
| U-C3 | Fail | `mmsi1 == mmsi2` pair | event yok | [ ] |

### 1.4 Safety index (`tests/test_safety_index.py`)

| ID | Tip | Senaryo | Beklenen | Done |
|----|-----|---------|----------|------|
| U-S1 | Happy | dolu wave/wind | score + status + `data_quality=ok` | [ ] |
| U-S2 | Fail | wave+sst null | `data_quality=unknown`; status **good değil** / skor tavanı (plan kuralı) | [ ] |
| U-S3 | Happy | payload | `baseline_boat_class` veya meta `question=now` (additive) | [ ] |

### 1.5 Bot / incidents normalize (`tests/test_bot.py`)

| ID | Tip | Senaryo | Beklenen | Done |
|----|-----|---------|----------|------|
| U-B1 | Happy | outlook fixture + `/balikci` | yanıtta saat aralığı (`HH:MM`) + level anlamı; skor tek başına değil | [ ] |
| U-B2 | Happy | return_by dolu | “en geç” / limana dönüş satırı | [ ] |
| U-B3 | Fail | outlook dosya yok | “derlenmedi” / info; exception yok; **openmeteo çağrılmadı** (mock assert) | [ ] |
| U-B4 | Happy | incidents **list** fixture + confirmed | `/kazalar` en az 1 satır | [ ] |
| U-B5 | Happy | incidents `{incidents:[...]}` | aynı | [ ] |
| U-B6 | Fail | incidents `{}` / null | dürüst boş mesaj; crash yok | [ ] |
| U-B7 | Happy | boat typo abone | coerce small; crash yok | [ ] |
| U-B8 | Security | area adına `<b>xss` | çıktıda raw tag yok (`&lt;` veya strip) | [ ] |

### 1.6 Telegram outlook metin (`tests/test_outlook.py` veya telegram test)

| ID | Tip | Senaryo | Beklenen | Done |
|----|-----|---------|----------|------|
| U-T1 | Happy | rough areas | mesajda saat satırları | [ ] |
| U-T2 | Happy | return_by | limana dönüş satırı | [ ] |
| U-T3 | Fail | areas boş | “Tahmin alınamadı” kalıbı; uydurma saat yok | [ ] |

### 1.7 Integration — orchestrator (hafif)

| ID | Tip | Senaryo | Beklenen | Done |
|----|-----|---------|----------|------|
| I-1 | Happy | `cycle` mock’lu outlook | `web/data/outlook.json` oluşur (tmp root) | [ ] |
| I-2 | Fail | outlook render raises | cycle devam; safety/straits hâlâ çağrılabilir (spy) | [ ] |

> I-1/I-2 pahalıysa: `run.py` hook’unun `try/except` ile sarıldığını unit + manuel yeterli sayılabilir; **DoD’da en az biri**.

### 1.8 Regresyon süiti (kırılmamalı)

```bash
pytest -q
ruff check src tests run.py
```

Özellikle: `test_outlook`, `test_bot`, `test_cpa`, `test_safety_index`, `test_sources` / fixture-leak.

---

## 2. Manuel test kontrol listesi (QA)

Ortam: local `py run.py --once` (ağ) **veya** fixture’ı `web/data/outlook.json` olarak kopyala + `py run.py --serve`.  
Prod: Pages URL + Telegram bot + (opsiyonel) Note 4.

### 2.1 Static API (`curl` / tarayıcı Network)

| # | Adım | Beklenen | Pass |
|---|------|----------|------|
| M-A1 | `GET /data/outlook.json` | 200 · `schema_version: 1` · `classes.small/medium/large` | [ ] |
| M-A2 | Body içinde ham 18 saatlik dizi yok | yalnız birleşik `windows` | [ ] |
| M-A3 | `GET /data/safety_index.json` | 200 · ratings | [ ] |
| M-A4 | `GET /data/incidents.json` | 200 · **array** (veya bilinen şekil) | [ ] |
| M-A5 | Outlook henüz yokken GET | 404 veya empty-policy; UI çökmez | [ ] |

### 2.2 Web UI — Happy path

| # | Adım | Beklenen | Pass |
|---|------|----------|------|
| M-U1 | Haritayı aç | `#outlook-panel` görünür (safety-strip civarı) | [ ] |
| M-U2 | Başlık/etiket **Bugün** okunur | Skor paneli değil | [ ] |
| M-U3 | Tekne = Küçük, bölge seç | Timeline segmentleri (ok/watch/danger renk + saat metni) | [ ] |
| M-U4 | Tekne = Büyük yap | Aynı bölgede pencereler **değişebilir** (daha yeşil) | [ ] |
| M-U5 | `return_by` varsa | “En geç HH:MM” görünür | [ ] |
| M-U6 | Hep ok bölge | Return satırı gizli; yeşil dilimler | [ ] |
| M-U7 | **Şimdi** satırı | Skor ikincil/soluk; Bugün’ün üstünde değil | [ ] |
| M-U8 | Select değiştir | Network’te yeni `outlook.json` GET **yok** (tek load / 60s) | [ ] |
| M-U9 | Dil EN | Label’lar EN key’lerle | [ ] |

### 2.3 Web UI — Loading / Empty / Error / Offline

| # | Adım | Beklenen | Pass |
|---|------|----------|------|
| M-E1 | Yavaş 3G veya ilk yük | Skeleton veya warm içerik; harita çalışır | [ ] |
| M-E2 | `outlook.json` sil / 404 simüle | Panel error/empty copy; sayfa beyaz ekran değil | [ ] |
| M-E3 | Boş `areas` fixture | “tahmin yok” empty; sahte saat yok | [ ] |
| M-E4 | DevTools Offline | `#offline-bar`; cache varsa panel dolu | [ ] |
| M-E5 | Stale summary | Mevcut `#stale` hâlâ çalışır | [ ] |

### 2.4 Web UI — Mobil / a11y

| # | Adım | Beklenen | Pass |
|---|------|----------|------|
| M-M1 | ~390px genişlik | Select stack / timeline scroll; taşma yok | [ ] |
| M-M2 | Klavye Tab | Select’lere focus | [ ] |
| M-M3 | Renk körü kontrolü | Saat + metin level (yalnız renk değil) | [ ] |

### 2.5 Telegram bot

| # | Adım | Beklenen | Pass |
|---|------|----------|------|
| M-T1 | `/balikci marmara` (veya kayıtlı bölge) | Saat pencereleri + tekne sınıfı | [ ] |
| M-T2 | Dönüş satırı | `return_by` varsa “en geç …” | [ ] |
| M-T3 | Şimdi bloğu | Varsa skor altta | [ ] |
| M-T4 | `/tekne` büyük + tekrar `/balikci` | Eşikler/pencereler sınıfına uygun (cache class) | [ ] |
| M-T5 | `/kazalar` | Crash yok; confirmed/probable veya dürüst boş | [ ] |
| M-T6 | Outlook dosyası yok (bot host) | “derlenmedi”; bot ayakta | [ ] |
| M-T7 | Note 4 (varsa) | Komut sırasında Open-Meteo trafiği yok (log/tcpdump opsiyonel) | [ ] |

### 2.6 Güvenlik / NFR smoke

| # | Adım | Beklenen | Pass |
|---|------|----------|------|
| M-S1 | Area XSS denemesi bot | HTML inject görünmez | [ ] |
| M-S2 | `outlook.json` içinde token/key yok | grep temiz | [ ] |
| M-S3 | Actions/cycle log | `[outlook] wrote` veya skip WARN; cycle tamam | [ ] |

---

## 3. Definition of Done (bitiş tanımı)

Merge / production **hazır** sayılması için **hepsinin** sağlanması gerekir.

### 3.1 İşlevsel DoD

- [ ] `outlook.json` cycle ile üretiliyor; şema v1 uyumlu  
- [ ] Web panel Bugün pencerelerini gösteriyor (3 sınıf)  
- [ ] `/balikci` pencere + `return_by` (uygunsa)  
- [ ] `/kazalar` list-shaped `incidents.json` ile doğru  
- [ ] CPA self-pair hygiene + test  
- [ ] Safety null → kör good/100 yok  
- [ ] Sample/live-fail → sahte outlook yok  

### 3.2 Kalite DoD

- [ ] Bölüm 1’deki zorunlu unit’ler yeşil (U-W*, U-R1–R6, U-C2–C3, U-S2, U-B1–B6, U-T*)  
- [ ] `pytest -q` tam süit yeşil  
- [ ] `ruff check` ilgili path’ler temiz  
- [ ] Bot hot path Open-Meteo import etmiyor (grep/test)  

### 3.3 Ürün / doküman DoD

- [ ] README `/balikci` + web vaadi gerçekle uyumlu  
- [ ] TODO/ARCHITECTURE drift güncel  
- [ ] Feature DoD maddeleri işaretli  
- [ ] En fazla 2 anlamlı commit; mesajlar *why* odaklı  
- [ ] Secrets commit’te yok  

### 3.4 Manuel QA DoD

- [ ] §2.2 Happy path M-U1–U8 pass  
- [ ] §2.3 en az M-E2 + M-E3 pass  
- [ ] §2.5 M-T1 + M-T5 pass  
- [ ] Prod/Pages: `curl` outlook 200 **veya** bir sonraki Actions sonrası planlı smoke  

### 3.5 Deploy DoD (prod’a çıkış kapısı)

- [ ] Pages’te `outlook.json` 200  
- [ ] Note 4 `git pull` + bot restart (kullanılıyorsa)  
- [ ] Telegram smoke `/balikci` + `/kazalar`  
- [ ] Site panel smoke  

### 3.6 Açıkça DoD dışı (engellemez)

- SDR, Redis, React, yeni endpoint avı  
- localStorage boat tercihi  
- Per-incident detay sayfası  
- %100 eval corpus büyütme  

---

## 4. Kabul kararı şablonu

```text
Özellik: outlook-cache-surfaces
Tarih:
Test eden:

Unit/Integration:  PASS / FAIL  (ek: pytest özeti)
Manuel Web:        PASS / FAIL
Manuel Bot:        PASS / FAIL
NFR/Security:      PASS / FAIL
DoD checklist:     PASS / FAIL

Karar:  ACCEPT  |  REJECT
Red nedeni (varsa):
```

**ACCEPT** yalnız tüm DoD kutuları doluysa.

---

## 5. Hızlı komut referansı

```bash
# Unit + lint
pytest -q
ruff check src tests run.py

# Local UI
py run.py --once --no-ais   # ağ varsa outlook üret
py run.py --serve

# Contract
curl -sS "$SITE/data/outlook.json" | python -m json.tool | head
```

---

*Kabul = “demo’da bir kez çalıştı” değil; happy + fail path testleri ve DoD kutularının tamamı.*
