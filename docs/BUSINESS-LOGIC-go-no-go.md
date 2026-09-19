# İş Mantığı ve Edge Case Analizi — Go / No-Go Window Alignment

| Alan | Değer |
|------|--------|
| **Özellik** | `outlook-cache-surfaces` |
| **Üst ilke (canlı kanaldan)** | *Saying nothing beats saying something false* — fixture/sahte pencere yok |
| **İlgili** | Feature · Data Model · API Contract |

---

## Planlanan iş mantığı (doldurulmuş)

1. Saatlik rüzgâr hamlesi + dalga, tekne sınıfı eşikleriyle `ok | watch | danger` pencerelerine birleşir.  
2. Aynı cycle’da 3 sınıf için hesaplanır → `outlook.json` atomik yazılır.  
3. Web / `/balikci` **Bugün** = pencere; **Şimdi** = skor (ikinci sınıf).  
4. `return_by` = ilk `danger.start`, yoksa ilk `watch.start`, yoksa `null`.  
5. Open-Meteo down / boş seri → dosya yazma veya boş `areas`; uydurma saat yok.  
6. Bot production path’te komut başına Open-Meteo çağırmaz.  
7. `/kazalar` dizi veya sarmalayıcı JSON; default confirmed+probable.  
8. CPA: unique MMSI + self-pair yok.

---

## 1. Çekirdek iş mantığı (Core Business Logic)

### 1.1 Girdi doğrulama (hesaptan önce)

| Kural ID | Kural | İhlalde |
|----------|--------|---------|
| V1 | `limits.gust_kn > 0` ve `limits.wave_m > 0` | O sınıfı atla / config default |
| V2 | `times`, `gusts`, `waves` uzunlukları hizalanır: `n = min(hours, len(times), …)` | `n == 0` → boş `AreaOutlook` |
| V3 | `gust` / `wave` slot `null` → `level_for` içinde `0.0` gibi davranır *(mevcut `window.py`)*; alan tamamen eksik seri ise area üretilmez | Boş windows |
| V4 | Area `name` boş/whitespace → satır atılır | Log |
| V5 | `BoatClassId` ∉ `{small,medium,large}` (bot/UI) → `small` | Sessiz coerce + log |
| V6 | Writer yalnız **live** Open-Meteo ile dolu outlook üretir (`SAMPLES_ALLOWED=false` prod) | Sample asla `outlook.json`’a yazılmaz |

### 1.2 Seviye hesabı (katı)

Mevcut `level_for` + `WATCH_AT = 0.75`:

| Koşul | Level |
|-------|--------|
| `gust >= gust_kn` **veya** `wave >= wave_m` | `danger` |
| `gust >= 0.75 * gust_kn` **veya** `wave >= 0.75 * wave_m` | `watch` |
| Aksi | `ok` |

- Eşikler **sınıfa özel**; skor motoru (`safety_index`) pencere seviyesini override edemez.  
- `worst(area) = max(windows.level)` rank: ok &lt; watch &lt; danger.

### 1.3 Pencere birleştirme

| Kural | Davranış |
|-------|----------|
| Ardışık aynı level | Tek `WindowSegment` (start sabit, end uzar; max gust/wave) |
| Kısa sakin “sliver” (`< min_hours`, default 2) daha sert bloğun arasında | Mevcut `_merge_slivers`: sakin dilim yutulur |
| `end` gün sonu | `"24:00"` geçerli |

### 1.4 `return_by` türetimi

```
if first window with level == danger:
    return_by = that.start
elif first window with level == watch:
    return_by = that.start
else:
    return_by = null
```

Metin: `return_by != null` → “Limana dönüş: en geç {return_by}”.  
`null` → satır **yazılmaz** (uydurma “23:59” yok).

### 1.5 Bugün vs Şimdi (ürün kuralı)

| Soru | Kaynak | Skor pencereyi geçersiz kılmaz |
|------|--------|--------------------------------|
| Bugün çıkılır mı, saat kaça? | `outlook.json` | Birincil |
| Şu an nasıl? | `safety_index.json` | İkincil; yoksa blok gizlenir |

`/balikci` sırası: (1) Bugün pencereleri (2) opsiyonel Şimdi (3) disclaimer.

### 1.6 Safety skor (yan mantık, bu feature’da sıkılaştırma)

| Kural | Davranış |
|-------|----------|
| `wave_m` ve `sea_temp_c` ikisi null | `data_quality=unknown`; skor tavanı düşür (örn. max 70 / status ≠ good) **veya** recommendation “ölçüm eksik” — kör 100 yasak |
| Tek null | `partial` |
| `has_storm_warning` | Mevcut alarm cezası |

### 1.7 Incidents listesi

| Kural | Davranış |
|-------|----------|
| Normalize sonrası dizi | Zorunlu |
| Default filter | `status ∈ {confirmed, probable}` |
| `limit` | 1..20, default 5 |
| Sıra | `last_update` / `first_seen` desc (mevcut sırayı koru; yoksa dizi sırası) |

### 1.8 CPA hygiene

| Kural | Davranış |
|-------|----------|
| Aynı `mmsi` birden fazla pozisyon | Son geçerli kazanır (dedupe map) |
| `mmsi1 == mmsi2` | Event üretilmez |
| Eksik lat/lon/mmsi | Aday listesine girmez |

### 1.9 Yazma atomikliği (cycle)

1. Bellekte tam `OutlookFile` kur.  
2. Validate invariant’lar.  
3. `outlook.json.tmp` yaz → `replace` ile `outlook.json` (Windows/Unix uyumlu `Path.replace`).  
4. Hata → eski dosya **kalır** (rollback = dokunmama); cycle diğer render’lara devam.

---

## 2. Olası edge case’ler

### 2.1 Null / undefined / boş

| Case | Sistem davranışı |
|------|------------------|
| Open-Meteo `hourly.time = []` | Outlook yazılmaz veya boş areas; bot/UI “tahmin yok” |
| Tek nokta live, diğeri down | Yalnız live noktalar; kısmi outlook **izinli** (en az 1 area) |
| `gusts[i]=null`, `waves[i]=null` | `level_for(0,0)` → genelde `ok` (mevcut); aşırı iyimserlik riski kabul / dokümante |
| Area name match yok (`/balikci xyz`) | Fallback: abone area → Marmara; “bulunamadı” yalnız her fallback fail ise |
| `outlook.json` yok (404) | UI banner; bot info mesajı; **asla** sample fixture |
| `safety_index` yok, outlook var | Yalnız Bugün bloğu |
| `incidents` `{}` veya `null` | Boş liste mesajı |
| `return_by` null, worst=ok | Dönüş satırı yok; “tüm gün sınır altında” dili |
| Abone `boat: "xlarge"` / typo | Coerce `small` |
| Abone `areas: []` | Config default / kanal sınıfı davranışı (mevcut outlook_text_for) |
| `generated` 24h+ eski (stale) | UI: stale uyarısı (summary `stale_hours` ile hizalı); yine de göster, uydurma yenileme yok |
| Çok uzun Telegram metni | 4096 kırp; bölgeleri kısalt (önce sakin bölgeleri drop) |

### 2.2 Eşzamanlılık / race

| Case | Davranış |
|------|----------|
| Actions cycle yazarken tarayıcı GET | Atomik replace → okuyucu eski **veya** yeni tam dosya; yarım JSON yok |
| İki cycle üst üste (workflow overlap) | Actions concurrency: mümkünse `cancel-in-progress` veya tek runner; overlap olursa son `replace` kazanır (last-write-wins). İdempotent içerik (aynı saat dilimi) |
| Note 4 bot okurken replace | OS atomic rename → bir read fail olursa bir sonraki komut retry; bot process crash etmez |
| Kullanıcı panel select spam | Client-side sync render; sunucu state yok → race yok |
| Sabah outlook + `/balikci` aynı anda | İkisi de aynı dosyayı okur; çift Telegram digest `sent.json` / `last_outlook` day key ile korunur (mevcut) |

### 2.3 Mükerrer işlem / idempotency

| İşlem | Anahtar | Tekrar davranışı |
|-------|---------|------------------|
| Cycle `outlook.json` yazımı | Yok (overwrite) | Aynı girdi → aynı çıktı; yan etki yok |
| Sabah kanal/abone outlook | `outlook:{date}` / `last_outlook == day` | İkinci cycle aynı gün göndermez |
| `/balikci` | İdempotent okuma | Her çağrı yeni mesaj (kasıtlı); spam koruması yok (Telegram rate — scope dışı) |
| `/kazalar` | İdempotent okuma | Aynı |
| CPA event → incident | Mevcut correlate / id | Self-pair düzelince yeni gürültü ID üretilmez |
| Fixture sample | `SAMPLES_ALLOWED` | Prod’da ikinci kez de yayınlanmaz |

### 2.4 Saat dilimi / sınır

| Case | Davranış |
|------|----------|
| UTC gece yarısı civarı slot | `_local_hhmm` + `tz_offset_hours` (TR +3); `24:00` end |
| `hours=18` gün ortasında | Mevcut openmeteo “current hour’dan kes” mantığı korunur |
| Yaz saati değişimi | Config sabit offset; otomatik DST yok (TR +3 sabit — OK) |

### 2.5 Güvenlik / yetki edge

| Case | Davranış |
|------|----------|
| Anon GET outlook | 200 public — PII yok |
| Bot token sızması | `.env` only; response’a path/token koyma |
| Abone dosyası git’e girerse | `.gitignore` — feature bunu bozmaz |

---

## 3. Hata & ağ yönetimi

### 3.1 Dış servis matrisi

| Servis | Fail modu | Fallback | Rollback |
|--------|-----------|----------|----------|
| **Open-Meteo** marine/wind | Timeout / 5xx / boş | `_net`: sample **yalnız** `SAMPLES_ALLOWED`; prod → down + boş | Eski `outlook.json` silinmez; yeni yazılmaz |
| **Open-Meteo kısmi** (wind OK marine FAIL) | wave null serisi | Area üretimi: wave 0 varsayımı mevcut; `data_quality` safety’de partial | — |
| **GitHub Pages** | 404 outlook | UI/bot “derlenmedi”; PWA eski cache (varsa) | — |
| **Telegram API** | 429 / 5xx | Mevcut notifier retry/log; kullanıcıya sessiz | Mesaj kuyruğu yok (basit) |
| **aisstream** (CPA yolu) | Burst fail | CPA incidents üretilmez; outlook etkilenmez | — |
| **Disk full / write error** | tmp yazılamadı | Log; replace yok → önceki artifact | Doğal rollback |
| **Yetkisiz (401/403) Pages** | Private/misconfig | Operatör; public API değil | — |

### 3.2 Timeout politikası

| Çağrı | Beklenen | Bu feature |
|-------|----------|------------|
| Open-Meteo (cycle) | Mevcut `_net` timeout | Yeni timeout icat etme; cycle `try/except` render_outlook |
| Bot → Telegram | Mevcut | Değişmez |
| Bot → Open-Meteo | **Yasak (prod)** | Timeout senaryosu yok; dosya yoksa kısa mesaj |
| Browser `fetch` outlook | `getJSON` fail → null | Banner; throw UI’ı kırmaz |

### 3.3 Fallback öncelik zinciri

**Outlook üretimi (cycle):**

```
live Open-Meteo points
  → build windows per class
    → validate
      → atomic write outlook.json
  else → do not write / write empty areas (seçim: tercihen DON'T WRITE if zero live points)
sample fixture → NEVER in production
```

**`/balikci` okuma:**

```
1. {repo}/web/data/outlook.json
2. (opsiyonel) GET site.url/data/outlook.json
3. stop → "henüz derlenmedi"
≠ fetch Open-Meteo
≠ samples/openmeteo_*.json
```

**Safety bloğu:**

```
safety_index var → Şimdi göster
yok → Bloğu atla (Bugün yeterli)
```

### 3.4 Rollback tanımı

| Katman | Rollback anlamı |
|--------|-----------------|
| DB transaction | Yok |
| Artifact | Başarısız yazımda önceki `outlook.json` korunur |
| Yanlış yayın (sample) | Prod’da imkânsız kılınır (V6); tespit edilirse manuel dosya sil + cycle |
| Kötü CPA | Hygiene sonrası yeni cycle gürültüyü büyütmez; eski incident prune/TTL |

### 3.5 Gözlemlenebilirlik

| Sinyal | Nerede |
|--------|--------|
| Open-Meteo live/down | `health.json` / `_net.STATUS` |
| Outlook render error | stdout `[outlook] render error: …` (cycle log) |
| Bot dosya yok | Kullanıcı info + log |
| Stale data | `summary.stale_hours` + UI banner |

Operator Telegram spam: `operator_alerts` kapalı kalır (mevcut); outlook fail kanalı kirletmez.

### 3.6 “Asla yapma” listesi (hata anında)

- Sample marine JSON’u outlook olarak yayınlamak  
- Skoru saat penceresi yerine uydurmak  
- `return_by` için rastgele saat  
- Note 4’te fail olunca Open-Meteo’ya flood  
- Yarım yazılmış JSON’u `replace` etmeden rename etmek  
- `/kazalar` parse hatasında stack trace’i kullanıcıya vermek  

---

## Test matrisi (edge → test)

| ID | Senaryo | Beklenen |
|----|---------|----------|
| E1 | Boş times | areas boş / no write |
| E2 | SAMPLES_ALLOWED false + dead API | outlook publish yok |
| E3 | incidents top-level array | `/kazalar` parse OK |
| E4 | incidents `{incidents:[]}` | OK |
| E5 | CPA aynı mmsi iki satır | tek aday; self pair 0 |
| E6 | return_by yalnız watch | watch.start |
| E7 | worst ok | return_by null; satır yok |
| E8 | safety wave+sst null | quality unknown; good/100 engeli |
| E9 | Atomic write mock fail | eski dosya durur |
| E10 | Bot boat typo | small |

---

## Özet karar tablosu

| Durum | Happy path dışı doğru cevap |
|-------|-----------------------------|
| Veri yok | Sessizlik / “derlenmedi” |
| Veri kısmi | Kısmi outlook (live noktalar) |
| Veri şüpheli (sample) | Yayın yok |
| Çift gönderim | Day-key idempotency |
| Çift yazım | Last-write-wins + atomic replace |
| Skor vs pencere çelişkisi | Pencere kazanır (Bugün) |

---

*Edge case’lerde başarı = yanlış emniyet vaadi vermemek; boş cevap, yanlış yeşil ışıldan iyidir.*
