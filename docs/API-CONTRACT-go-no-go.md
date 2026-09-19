# API ve Entegrasyon Sözleşmesi — Go / No-Go Window Alignment

| Alan | Değer |
|------|--------|
| **Özellik** | `outlook-cache-surfaces` |
| **API stili** | **Read-only Static JSON API** (GitHub Pages) + **Telegram Bot command surface** (RPC-benzeri) |
| **Base URL (prod)** | `https://keremkalyoncu.github.io/maritime-watch` |
| **Base URL (local)** | `http://127.0.0.1:8000` (`run.py --serve`) |
| **Auth** | Public GET — API key / Bearer **yok** |
| **İlgili** | `DATA-MODEL-go-no-go.md` · `ARCHITECTURE-MAP-go-no-go.md` |

---

## API ihtiyacı (doldurulmuş)

Bu feature için gereken çağrılar:

1. **Web UI** → `GET .../data/outlook.json` ile Bugün pencerelerini almak; mevcut `safety_index.json` / `incidents.json` ile Şimdi + olay birleştirmek.  
2. **Note 4 bot** → Aynı `outlook.json` (ve incidents/safety) dosyalarını **diskten veya isteğe bağlı HTTPS GET** ile okuyup `/balikci`, `/kazalar` yanıtlamak.  
3. **Yazma API’si yok** — üretimi yalnız `run.py` cycle (Actions) yapar; istemci `POST/PUT/PATCH/DELETE` göndermez.

Klasik REST “create outlook” endpoint’i **yok ve scope dışı**. Aşağıdaki sözleşme mevcut mimariyi netleştirir; uydurma CRUD eklemez.

---

## 1. Endpoint & HTTP Method

### 1.1 Public Static Data API (istemci ↔ Pages)

Tüm yollar `Content-Type: application/json; charset=utf-8` (Pages’in servis ettiği gibi).  
Method: **yalnızca `GET`** (ve otomatik `HEAD`).

| # | Method | Path | Amaç | Bu feature |
|---|--------|------|------|------------|
| D1 | `GET` | `/data/outlook.json` | Bugün · 3 tekne sınıfı · saat pencereleri | **YENİ — birincil** |
| D2 | `GET` | `/data/safety_index.json` | Şimdi · skor | Mevcut; additive alanlar |
| D3 | `GET` | `/data/incidents.json` | Olay listesi | Mevcut; bot okuyucu toleransı |
| D4 | `GET` | `/data/warnings.json` | Uyarılar | Dokunulmaz |
| D5 | `GET` | `/data/summary.json` | Sayaç / stale | Dokunulmaz |
| D6 | `GET` | `/data/health.json` | Kaynak sağlığı | Dokunulmaz |
| D7 | `GET` | `/data/straits.json` | Boğaz özeti | Dokunulmaz |
| D8 | `GET` | `/data/weather_overlay.json` | Harita vektörleri | Dokunulmaz |
| D9 | `GET` | `/data/feed.xml` | RSS (`application/rss+xml`) | Dokunulmaz |
| D10 | `GET` | `/data/regions.geojson` | Bölge poligonları | Dokunulmaz |

**Query string:** Sunucu tarafında filtre **yok**. İstemci `?t=Date.now()` cache-bust kullanabilir (mevcut `getJSON` davranışı). Sunucu query’yi ignore eder.

**Tam örnek URL’ler:**

```
GET https://keremkalyoncu.github.io/maritime-watch/data/outlook.json
GET https://keremkalyoncu.github.io/maritime-watch/data/safety_index.json
GET https://keremkalyoncu.github.io/maritime-watch/data/incidents.json
```

### 1.2 Bilinçli olarak açılmayan HTTP API’ler

| Method | Path | Durum |
|--------|------|--------|
| `POST` | `/api/outlook` | Yok — Out of Scope |
| `PUT/PATCH` | `/api/subscribers` | Yok — abonelik Telegram’da |
| `DELETE` | `*` | Yok |
| `GET` | `/api/v1/...` | Yok — versiyon path’te değil, JSON `schema_version` içinde |

### 1.3 Telegram Bot surface (entegrasyon “endpoint”leri)

HTTP olarak bot **Telegram Bot API**’ye konuşur; kullanıcıya görünen sözleşme komutlardır.

| Komut (kullanıcı) | Bot içi handler | Okunan artifact | Yazma |
|-------------------|-----------------|-----------------|-------|
| `/balikci [bölge]` | `_fisherman_text` | `outlook.json` + opsiyonel `safety_index.json` | Yok (yanıt mesajı) |
| `/durum` | mevcut outlook yolu | `outlook.json` tercih | Yok |
| `/kazalar` | `_incidents_text` | `incidents.json` | Yok |
| `/tekne` · `/bolge` | abone state | `bot_subscribers.json` | Local disk |

**Dış HTTP (bot → Telegram):**

| Method | URL | Kullanım |
|--------|-----|----------|
| `GET` | `https://api.telegram.org/bot<TOKEN>/getUpdates` | Long poll (Note 4) |
| `POST` | `https://api.telegram.org/bot<TOKEN>/sendMessage` | HTML yanıt |

Token asla client’a veya `web/data`’ya konmaz.

### 1.4 Edge disk sözleşmesi (Note 4 — HTTP değil)

Prod bot tercihen repo/`web/data` kopyasını okur:

```
file://{repo}/web/data/outlook.json
```

Actions commit etmeden önce Pages’te dosya yoksa bot `GET` base URL’ye düşebilir (opsiyonel); **canlı Open-Meteo yok**.

---

## 2. Request Payload & Validasyon

### 2.1 `GET /data/outlook.json`

| Parça | Kural |
|-------|--------|
| **Headers (istemci)** | `Accept: application/json` (opsiyonel). `Authorization` gönderilmez. |
| **Body** | **Yasak / yok** — body varsa sunucu (statik host) ignore eder. |
| **Query** | Opsiyonel cache-bust: `^\?_?\w+=\d+$` (bilgi amaçlı; validate edilmez). |

Sunucu-side request validasyonu yok (statik dosya). **İstemci-side** kullanım validasyonu:

| Alan (istemci seçimi) | Zorunlu | Kural |
|-----------------------|---------|--------|
| `boat` | Evet (UI default) | `^(small\|medium\|large)$` |
| `area` | Evet (UI default) | `outlook.classes[boat].areas[].name` içinde exact match; yoksa ilk area veya hata mesajı |
| Panel state length | — | `area` max 80 karakter (UI) |

### 2.2 `GET /data/safety_index.json` · `GET /data/incidents.json`

Aynı: body yok, auth yok.  
`incidents` için **istemci normalize** (bot):

| Girdi | Validasyon |
|-------|------------|
| `Array.isArray(data)` | → kullan |
| `data && Array.isArray(data.incidents)` | → `data.incidents` |
| Aksi | → boş liste / kullanıcıya “kayıt yok” (500 uydurma) |

`/kazalar` filtre (bot içi, HTTP değil):

| Alan | Default | Kural |
|------|---------|--------|
| `statuses` | `confirmed`, `probable` | Enum ⊆ `signal\|probable\|confirmed\|resolved\|false-positive` |
| `limit` | `5` | integer `1..20` |

`/balikci` argüman (bot içi):

| Alan | Zorunlu | Kural |
|------|---------|--------|
| `area_arg` | Hayır | Trim; max 64 char; fuzzy match mevcut `_match_area`; match yoksa fallback zinciri |
| `boat` | Aboneden | Enum `BoatClassId`; yoksa `small` |

### 2.3 Telegram `sendMessage` (bot → Telegram) — referans

| Alan | Zorunlu | Kural |
|------|---------|--------|
| `chat_id` | Evet | Telegram id |
| `text` | Evet | Max ~4096 char (Telegram limiti); aşarsa kısalt |
| `parse_mode` | Evet | `HTML` |
| `disable_web_page_preview` | Önerilir | `true` |

### 2.4 Writer-side (cycle) — “request” değil, üretici invariant

`render_outlook` yazmadan önce doğrular:

| Alan | Kural | İhlalde |
|------|--------|---------|
| `schema_version` | `=== 1` | Yazma / log error |
| `classes.small\|medium\|large` | üçü de object | Fail-soft: cycle devam, outlook atlanır |
| `hours` | int `1..48` | config clamp |
| `tz_offset_hours` | number `-12..14` | config |
| `areas[].windows[].level` | `ok\|watch\|danger` | skip window |
| `return_by` | `null` veya `^([01]\d\|2[0-3]):[0-5]\d$` | null’a çek |
| Dosya boyutu | hedef &lt; ~256 KB | ham seri yazma yasak |

---

## 3. Response Formatları & HTTP Kodları

Statik hosting gerçekliği: çoğu hata **uygulama JSON’u değil**, CDN/Pages HTTP’idir. Sözleşme her iki katmanı da tanımlar.

### 3.1 Başarılı — `GET /data/outlook.json`

**HTTP `200 OK`**

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: max-age=0, must-revalidate   # veya Pages default
```

```json
{
  "schema_version": 1,
  "generated": "2026-09-19T05:02:34Z",
  "hours": 18,
  "tz_offset_hours": 3,
  "question": "today",
  "classes": {
    "small": {
      "label": "küçük tekne (8 m ve altı)",
      "limits": { "label": "küçük tekne (8 m ve altı)", "gust_kn": 22, "wave_m": 1.25 },
      "areas": [
        {
          "name": "Marmara Denizi",
          "lat": 40.7,
          "lon": 28.2,
          "windows": [
            {
              "start": "06:00",
              "end": "15:00",
              "level": "ok",
              "gust_kn": 14.0,
              "wave_m": 0.6
            },
            {
              "start": "15:00",
              "end": "18:00",
              "level": "watch",
              "gust_kn": 20.0,
              "wave_m": 1.1
            },
            {
              "start": "18:00",
              "end": "24:00",
              "level": "danger",
              "gust_kn": 26.0,
              "wave_m": 1.4
            }
          ],
          "max_gust": 26.0,
          "max_wave": 1.4,
          "first_danger_start": "18:00",
          "return_by": "18:00",
          "worst": "danger"
        }
      ]
    },
    "medium": { "label": "…", "limits": {}, "areas": [] },
    "large": { "label": "…", "limits": {}, "areas": [] }
  }
}
```

`limits.label` tekrarı implementasyonda sadeleştirilebilir; okuyucu `BoatClassOutlook.label` veya `limits.label` kabul eder.

### 3.2 Başarılı — `GET /data/safety_index.json` (`200`)

```json
{
  "schema_version": 1,
  "generated": "2026-09-19T05:02:34Z",
  "question": "now",
  "ratings": [
    {
      "area": "Marmara Denizi",
      "score": 72,
      "status": "caution",
      "wave_m": null,
      "wind_kn": 4.0,
      "gust_kn": 5.0,
      "recommendation_tr": "…",
      "recommendation_en": "…",
      "sea_temp_c": null,
      "current_kn": null,
      "last_update": "2026-09-19T05:02:34Z",
      "data_quality": "unknown",
      "baseline_boat_class": "small"
    }
  ]
}
```

### 3.3 Başarılı — `GET /data/incidents.json` (`200`)

Writer (mevcut):

```json
[
  {
    "id": "2026-09-17-ais-79e1c1",
    "type": "drift",
    "status": "signal",
    "confidence": 0.35,
    "severity": "minor",
    "lat": 36.44,
    "lon": 28.23,
    "area": "Güney Ege",
    "vessel": { "name": "SAONISOS", "mmsi": 239775900, "type": null, "callsign": null },
    "summary": null
  }
]
```

Okuyucu ayrıca şunu da kabul eder (üretilmez):

```json
{ "incidents": [ /* ... */ ], "generated": "2026-09-19T05:02:34Z" }
```

### 3.4 HTTP hata matrisi (Static Data API)

| Kod | Ne zaman | İstemci davranışı | JSON gövde |
|-----|----------|-------------------|------------|
| **200** | Dosya var | Parse + UI/bot render | `OutlookFile` / ilgili şema |
| **304** | `If-None-Match` / cache (nadir Pages) | Önceki gövdeyi kullan | Boş |
| **404** | Henüz üretilmemiş / yanlış path | UI: “Outlook henüz derlenmedi”; bot aynı | Pages HTML veya boş — **uygulama error JSON yok** |
| **403** | Repo/Pages private (beklenmez) | Operatör uyarısı | Host HTML |
| **401** | Bu API’de kullanılmaz | — | — |
| **400** | Static GET’te pratikte yok | — | — |
| **5xx** | Pages/CDN arıza | Retry backoff; stale SW cache (PWA) | Host HTML |
| **Network fail** | Offline | PWA: son cache; yoksa banner | — |

**Uygulama-seviyesi hata JSON’u (isteğe bağlı istemci normu)** — sunucu dönmez; `getJSON` null sonrası UI üretir:

```json
{
  "ok": false,
  "error": {
    "code": "OUTLOOK_UNAVAILABLE",
    "message_tr": "Bugünün çıkış penceresi henüz derlenmedi. Bir sonraki güncelleme döngüsünü bekleyin.",
    "message_en": "Today's departure windows are not ready yet.",
    "http_status": 404
  }
}
```

### 3.5 Şema geçerli ama iş kuralı boş (`200` + boş areas)

Open-Meteo down → fail-soft: dosya yazılmamış (**404**) **veya** boş areas ile **200**:

```json
{
  "schema_version": 1,
  "generated": "2026-09-19T05:02:34Z",
  "hours": 18,
  "tz_offset_hours": 3,
  "question": "today",
  "classes": {
    "small": { "label": "küçük tekne (8 m ve altı)", "limits": { "gust_kn": 22, "wave_m": 1.25, "label": "küçük tekne (8 m ve altı)" }, "areas": [] },
    "medium": { "label": "…", "limits": {}, "areas": [] },
    "large": { "label": "…", "limits": {}, "areas": [] }
  }
}
```

İstemci: `areas.length === 0` → “Tahmin alınamadı” (mevcut outlook metin kalıbı). **Sahte pencere basılmaz.**

### 3.6 Bot “response” (HTTP değil — kullanıcıya görünen başarı)

Başarı = Telegram `sendMessage` → Bot API `200` + `"ok": true`.

Kullanıcıya giden mantıksal başarı şablonu (`/balikci`):

```text
🎣 {area} · Bugün
Tekne: {label}

🟢 08:00–15:00 uygun …
🟡 15:00–18:00 dikkat …
🔴 18:00 sonrası çıkma …

💡 Limana dönüş: en geç {return_by}

——— Şimdi (anlık skor) ———
Skor: {score}/100 · {status}
…

⚠️ Model tahminidir …
```

Bot içi hata (Telegram’a yine 200 mesaj; “API 500” taklit edilmez):

| Durum | Kullanıcı metni |
|-------|-----------------|
| outlook dosya yok | `ℹ️ Bugünün penceresi henüz derlenmedi…` |
| area yok | `ℹ️ {area} için pencere bulunamadı.` |
| incidents boş filtre | `🌊 … aktif kaza … bulunmuyor.` |
| parse hata | `⚠️ … okunamadı` (detay kısalı; token/path sızdırma) |

### 3.7 CORS

Aynı origin (Pages’ten servis edilen `index.html` → `/data/*`): CORS gerekmez.  
Başka origin’den tüketim resmi desteklenmez (scope dışı); Pages genelde `Access-Control-Allow-Origin: *` vermez — üçüncü parti embed vaat etme.

---

## Entegrasyon özeti (kim kimi çağırır)

```
[GitHub Actions run.py]
        │ write
        ▼
[GitHub Pages /data/*.json]  ←── GET ──  [Browser app.js]
        ▲                         ←── read file / GET ──  [Note4 Bot]
        │
[Telegram servers]  ←── getUpdates / sendMessage ──  [Note4 Bot]
```

---

## Sözleşme versioning

| Mekanizma | Değer |
|-----------|--------|
| URL version | Yok (`/api/v1`) |
| Payload | `schema_version: 1` |
| Breaking change | `schema_version: 2` + Feature doc; eski web kısa süre toleranslı parse |

---

## Test sözleşmesi (contract tests)

1. `test_render_outlook`: üretilen JSON `OutlookFile` zorunlu alanları.  
2. `test_bot`: fixture `outlook.json` ile `/balikci` saat satırı içerir.  
3. `test_bot`: `incidents.json` dizi fixture → `/kazalar` boş değil (confirmed varsa).  
4. Manuel: `curl -sI $BASE/data/outlook.json` → `200` (cycle sonrası).

---

*Bu sözleşme REST CRUD icat etmez; Static GET + Telegram komut yüzeyini tip ve hata davranışıyla kilitler.*
