# Güvenlik, Performans ve Non-Functional Gereksinimler — Go / No-Go

| Alan | Değer |
|------|--------|
| **Özellik** | `outlook-cache-surfaces` |
| **Ortam** | Public GitHub Pages (okuma) · Actions cycle (yazma) · Note 4 Termux bot (hafif okuma) |
| **Üst sınırlar (öncelik)** | Note 4: ek Open-Meteo yok · `outlook.json` ≪ 256 KB · az GitHub commit · sample asla prod publish |
| **İlgili** | API Contract · Business Logic · UI/UX |

---

## Güvenlik / performans öncelikleri (doldurulmuş)

1. **Yanlış emniyet verisi = güvenlik olayı** (fixture sızıntısı sınıfı) — confidentiality’den önce integrity.  
2. **XSS**: Telegram `parse_mode=HTML` + web DOM; tüm dinamik metin escape.  
3. **Secrets**: bot token / AIS key asla `web/data` veya commit.  
4. **Note 4**: CPU/RAM/TLS bütçesi — komut path’inde dış hava API yok.  
5. **PII**: abone chat id host’ta; outlook artifact’ta kişi yok.  
6. Redis / SQL / RBAC middleware **yok** — NFR’ler bu gerçekliğe map edilir, uydurma stack eklenmez.

---

## 1. Güvenlik & yetkilendirme

### 1.1 RBAC / erişim modeli

Klasik RBAC tablosu yok. Mantıksal roller:

| Rol | Kim | Ne yapabilir | Ne yapamaz |
|-----|-----|--------------|------------|
| `anonymous_public` | Tarayıcı / crawler | `GET /data/*.json`, harita | Yazma, abone listesi, `.env` |
| `actions_publisher` | GitHub Actions (`GITHUB_TOKEN` + secrets) | Cycle çalıştır, artifact üret, Pages’e push | Kullanıcı RBAC yönetmez |
| `bot_runtime` | Note 4 process + `TELEGRAM_BOT_TOKEN` | `getUpdates` / `sendMessage`; local `web/data` + `bot_subscribers.json` oku/yaz | Public write API |
| `operator` | Repo admin | Secrets, workflow, SSH Note 4 | — |

**Middleware:** Express/JWT yok. Kontroller:

- Pages: repo public → bilinçli açık veri.  
- Actions: `secrets.*` yalnızca runner env.  
- Bot: token process env; HTTP API’siz.

Bu feature **yeni rol / auth endpoint eklemez**.

### 1.2 Input sanitization

| Yüzey | Girdi | Kural |
|-------|-------|--------|
| Web select `boat` | string | Allowlist `small\|medium\|large`; aksi → `small` |
| Web select `area` | string | Exact match area names; max 80 char; DOM text `textContent` veya escape |
| Bot `/balikci` arg | string | Trim; max 64; `_match_area`; HTML’e basmadan `html.escape` |
| Bot diğer komutlar | mevcut | Aynı escape disiplini |
| Outlook writer | Open-Meteo numbers | `float` coerce; NaN → skip slot |
| Area `name` from API/config | string | Escape on Telegram; web `textContent` |

**SQL injection:** SQL yok → N/A.  
**NoSQL / command injection:** `subprocess` outlook path’te yok. Path join yalnız güvenilir `cfg["_root"]` + sabit `"web/data/outlook.json"`.

### 1.3 XSS / HTML injection

| Kanal | Risk | Önlem |
|-------|------|--------|
| Telegram HTML | Yüksek | Mevcut kalıp: `html.escape` tüm kullanıcı/area/label alanlarında; `/balikci` yeni satırlar **aynı** |
| `innerHTML` web | Orta | Timeline segmentleri: tercih `textContent` + CSS class; `innerHTML` kullanılıyorsa yalnız allowlist’li sabit şablon + escape edilmiş saatler |
| `outlook.json` kötü contents | Düşük (biz yazarız) | Yine de client escape — defense in depth |
| SVG/logo | Mevcut | Değişmez |

**CSP:** Bu feature’da yeni CSP header ekleme zorunlu değil (Pages kontrolü sınırlı); mevcut CDN Leaflet bırakılır.

### 1.4 CSRF / CORS / authz

| Konu | Durum |
|------|--------|
| CSRF | State-changing browser API yok → N/A |
| CORS | Aynı origin; üçüncü parti API vaat edilmez |
| IDOR | Abone dosyası public değil; chat_id URL’de yok |
| Path traversal | Sabit dosya adları; user path concat yok |

### 1.5 Veri bütünlüğü (emniyet-güvenlik)

| Kontrol | Gereksinim |
|---------|------------|
| Sample publish | Prod `SAMPLES_ALLOWED=false` → outlook’a sample yazmak **P0 bug** |
| Atomic write | `tmp` + `replace` — yarım JSON yok |
| Schema | `schema_version: 1` validate before publish |
| Disclaimer | UI + Telegram’da model uyarısı kalır (yasal / ethik NFR) |

### 1.6 Gizlilik (KVKK-yan)

| Veri | Nerede | Feature etkisi |
|------|--------|----------------|
| Chat id | `bot_subscribers.json` gitignore | Outlook JSON’a **yazılmaz** |
| GPS `/neredeyim` | Geçici mesaj | Bu feature dokunmaz |
| Victim names | `privacy.py` | Outlook’ta yok |

### 1.7 Secrets checklist

- [ ] `TELEGRAM_*`, `AISSTREAM_KEY` → `.env` / Actions secrets  
- [ ] `web/data/outlook.json` içinde token/url secret yok  
- [ ] Hata mesajlarında path + token yok  
- [ ] Log’larda `Authorization` yok  

---

## 2. Performans kriterleri

### 2.1 “N+1 / DB” karşılığı

SQL yok. Anti-pattern karşılıkları:

| Klasik | Bu projede yasak / sınır |
|--------|---------------------------|
| N+1 query | Bot’ta her abone için Open-Meteo N çağrı — **yasak**; 1× cycle → 1 dosya → N okuma local |
| Chatty API | Web’in her select’te `GET outlook.json` — **yasak**; 1 fetch / 60s refresh, select local filter |
| Huge join | `outlook.json` içine ham hourly seri — **yasak** |

**Hedef:** Cycle’da Open-Meteo nokta sayısı mevcut config ile aynı kalsın; ek sınıf maliyeti yalnız CPU `window.build` × 3.

### 2.2 Caching stratejisi

| Katman | Mekanizma | TTL / not |
|--------|-----------|-----------|
| Open-Meteo process | Mevcut `_FORECAST_CACHE` ~900s | Redis **yok**; Memory yeterli |
| `outlook.json` | Disk + Pages CDN | Her cycle yenilenir (~15 dk) |
| Browser | `getJSON` cache-bust query; SW network-first `/data/*` | Mevcut PWA |
| Note 4 | Dosya mtime isteğe bağlı (opsiyonel) | Zorunlu değil; her komutta okuma &lt; 256KB OK |
| Redis | **Eklenmez** | Out of scope |

### 2.3 Pagination

| Kaynak | Strateji |
|--------|----------|
| Outlook areas | Tam liste (≈ on’lu dil); sayfalama yok |
| `/kazalar` | `limit=5` (max 20) — soft pagination |
| Web timeline incidents | Mevcut UI; bu feature değiştirmez |
| Outlook windows / area | Zaten birleşik segment; saatlik 18 satır basılmaz |

### 2.4 Rate limiting

| Yüzey | Limit | Davranış |
|-------|-------|----------|
| Telegram send | Mevcut notifier hız sınırı | Koru; outlook mesajı bunu bypass etmesin (digest kuralları) |
| Bot long poll | Mevcut 20s timeout | Note 4 güç bütçesi |
| Open-Meteo | Cycle sıklığı ≤ cron | Komut path 0 çağrı |
| Public GET Pages | CDN; app-level rate limit yok | Abuse = static cost only |
| Actions | Workflow concurrency | Mümkünse tek run; overlap last-write-wins |

**Yeni Redis rate limiter yok.**

### 2.5 Performans bütçeleri (SLO / soft)

| Metrik | Hedef |
|--------|-------|
| `outlook.json` boyutu | &lt; 256 KB (hedef &lt; 64 KB tipik) |
| `render_outlook` CPU (Actions) | Mevcut cycle + &lt; ~2–5 s ek (nokta sayısına bağlı) |
| Note 4 `/balikci` latency | &lt; 500 ms disk okuma + format (ağsız) |
| Web panel first paint | İlk `getJSON` ile diğer data paralel; haritayı bloklamaz |
| Memory Note 4 | Tüm outlook parse &lt; birkaç MB peak |

### 2.6 Note 4 özel NFR

- Outlook üretimi Note 4’e **taşınmaz**.  
- Bot restart sonrası soğuk okuma OK.  
- Swap thrash önlemek: büyük `events.jsonl` okuma `/balikci` path’inde yok.

---

## 3. Loglama ve izlenebilirlik

Mevcut stil: `print(f"[tag] ...")` stdout (Actions log). Yeni ELK/Sentry zorunlu değil.

### 3.1 Tag ve seviye sözleşmesi

Seviye prefix (metin): `[outlook]`, `[outlook:warn]`, `[outlook:error]` — veya `INFO/WARN/ERROR` kelimesi.

| Aşama | Seviye | Örnek |
|-------|--------|--------|
| Render başı | INFO | `[outlook] building classes=3 points=N` |
| Live nokta 0 | WARN | `[outlook:warn] no live forecast points — skip write` |
| Sample engellendi | WARN | `[outlook:warn] refusing sample-backed outlook` |
| Validate fail | ERROR | `[outlook:error] schema validation failed: …` |
| Atomic write OK | INFO | `[outlook] wrote web/data/outlook.json bytes=…` |
| Write exception | ERROR | `[outlook:error] write failed: …` (+ cycle devam) |
| Bot file missing | INFO | `[bot] outlook.json missing — user notified` |
| Bot parse fail | ERROR | `[bot] outlook parse error: …` (no stack to user) |
| `/balikci` OK | DEBUG/INFO | Opsiyonel; prod’da her komutu spamleme — **default sessiz** veya sayaç |
| Open-Meteo down | Mevcut `_net.STATUS` | `health.json` |
| CPA hygiene drop | DEBUG | Self-pair count (test/log sparse) |

### 3.2 Hata yakalama blokları

```
run.py cycle:
  try:
      render_outlook(...)
  except Exception as e:
      print ERROR
      # no raise — fail-soft (straits/safety kalıbı)

bot._fisherman_text:
  try:
      load + format
  except Exception as e:
      print ERROR
      return kısa kullanıcı mesajı

telegram send:
  mevcut try/timeout/rate — değişmez
```

**Yasak:** bare `except:` sessiz yutma; token’lı traceback kullanıcıya.

### 3.3 Metrik / health

| Sinyal | Nerede |
|--------|--------|
| Outlook var mı / taze mi | Dolaylı: dosya `generated` + UI; isteğe bağlı `health.sources.outlook` **zorunlu değil** (scope şişmesin) |
| Sources live/down | `health.json` mevcut |
| Cycle süresi | `health.cycle_seconds` |

### 3.4 Alerting

| Koşul | Kanal |
|-------|-------|
| ≥3 kaynak down | Mevcut operator (config kapalıysa log only) |
| Outlook N cycle yazılamadı | Actions log inceleme; public kanal spam yok |
| Telegram 401 | ERROR log — secret rotate |

### 3.5 Log retention / PII

- Actions log: GitHub retention.  
- Chat id / GPS bot log’a **yazılmaz** (özellikle INFO spam).  
- Area adları OK (kamuya açık deniz bölgeleri).

---

## 4. Diğer non-functional

| Alan | Gereksinim |
|------|------------|
| Availability | Pages + cron best-effort; outlook eksikse degrade (harita çalışır) |
| Durability | Önceki `outlook.json` failed write’da kalır |
| Consistency | Bugün vs Şimdi etiketleri bozulmaz |
| Compatibility | Python 3.11–3.13 CI; Note 4 bot JSON-only |
| Accessibility | UI-UX doc (aria-live, kontrast) |
| Legal | Kurtarma servisi değil disclaimer korunur |

---

## 5. Doğrulama checklist (prod öncesi)

**Güvenlik**

- [ ] `/balikci` area/label escape unit test  
- [ ] Sample + dead API → outlook yazılmadı testi  
- [ ] Secrets grep `web/data`  

**Performans**

- [ ] Fixture outlook boyutu assert &lt; 256KB  
- [ ] Bot path’te openmeteo import yok (lint/test)  
- [ ] Select change network waterfall yok (manuel)  

**Gözlem**

- [ ] Actions log’da `[outlook] wrote` veya skip WARN  
- [ ] Fail-soft: outlook exception cycle’ı öldürmez  

---

## 6. Bilinçli olarak eklenmeyecek NFR çözümleri

- Redis / Memcached  
- SQL index / ORM N+1 tooling  
- JWT RBAC middleware  
- WAF / API gateway  
- Datadog/Sentry zorunluluğu (isteğe bağlı sonra)  
- Aggressive client rate limit UI  

---

*NFR özeti: emniyet bütünlüğü + XSS escape + Note 4’te sıfır ekstra API + küçük JSON + fail-soft log.*
