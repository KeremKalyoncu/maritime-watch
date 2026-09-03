# Maritime Watch

**Türkiye karasuları için deniz olayı erken-uyarı ve şeffaflık aracı.**
AIS anomalilerini, resmi açıklamaları (Sahil Güvenlik / AFAD) ve denizcilik hava
uyarılarını (Meteoroloji Genel Müdürlüğü) tek akışta birleştirir; sonucu bir
haritada, bir RSS beslemesinde ve isteğe bağlı bir Telegram önleme kanalında
yayınlar.

> Bu bir kurtarma servisi **değildir**. Acil durumda **158** (Sahil Güvenlik) /
> **112**. Araç yalnızca kamuya açık / resmi bilgiyi hızlı ve tek yerde toplar.

---

## Ne sağlar

| Kullanıcı | Aldığı şey |
| :-- | :-- |
| Balıkçı / küçük tekne | Opt-in Telegram kanalı: *"Yarın Marmara'da 7-8 Bofor lodos, fırtına uyarısı"* — resmi uyarı, sade Türkçe |
| Gazeteci / araştırmacı / vatandaş | Web haritası + zaman çizelgesi: AIS anomalileri + DSC + resmi açıklamalar, her kayıtta kaynak linki ve **doğrulanmadı** etiketi |
| Haber merkezi | `feed.xml` (RSS) — olay akışını kendi sistemine bağlar |

Ne sağlamaz: kurtarma yapmaz (o Sahil Güvenlik'in işi), AIS'i olmayan tekneleri
(göçmen botlarının çoğu) göremez, "ilk duyan biz" garantisi vermez.

---

## Veri kaynakları

| Kaynak | Ne getirir | Anahtar? | Durum |
| :-- | :-- | :-- | :-- |
| **aisstream.io** | Gemi konumu + AIS anomali + AIS-SART/MOB + güvenlik yayını (msg 14) | evet (bedava) | canlı |
| **Open-Meteo** (marine + forecast) | Dalga yüksekliği + rüzgar hamlesi tahmini | hayır | canlı |
| **AFAD + USGS + EMSC** | Kıyıya yakın depremler, üç kurum çapraz doğrulamalı | hayır | canlı |
| **Sahil Güvenlik** | Resmi kurtarma açıklamaları | hayır | canlı (scrape) |
| **Haber RSS** (AA, Hürriyet, NTV, Sözcü, CNN Türk, TRT, Habertürk, Milliyet, Denizhaber, gCaptain) | Kelime-sınırı filtreli denizcilik haberleri → teyit | hayır | canlı |
| **GDACS** (RSS) | Bölgesel afet uyarıları (fırtına, sel, kasırga) | hayır | canlı |
| **NASA EONET** | Doğa olayları (şiddetli fırtına, yangın, sel) | hayır | canlı |
| **aviationweather.gov METAR** | Kıyı havaalanı rüzgar / görüş / fırtına | hayır | canlı |
| **NGA NAVAREA III** | Seyir uyarıları | hayır | endpoint şu an 404, kod hazır |
| **ReliefWeb** | Türkiye afet raporları | hayır | API v1 kapandı (410), kod hazır |
| MGM deniz uyarısı | — | — | kararlı endpoint yok, Open-Meteo kapsıyor |
| **SDR** (DSC / NAVTEX / Ch16) | yapısal tehlike / MSI / ses | — | opsiyonel modül, varsayılan kapalı |

**Çift kayıt birleştirme:** Aynı tehlikeyi (deprem / hava / afet) birden çok
kaynak verirse tek kayıtta toplanır; harita ve Telegram *"N bağımsız kaynak
doğruluyor"* der (`src/process/dedup.py → same_hazard`). Konum + zaman + (deprem
için) büyüklük yakınlığına bakar.

```mermaid
flowchart LR
    A1[aisstream.io] --> P[process]
    A2[Open-Meteo] --> P
    A3[AFAD deprem] --> P
    A4[Sahil Güvenlik] --> P
    A5[Haber RSS] --> P
    A6[GDACS / METAR] --> P
    A7[(opsiyonel) SDR] -. belgelenmiş .-> P
    P --> N[normalize + dedup/correlate]
    N --> C[classify\nstatus · confidence · geocode]
    C --> S[(JSON store\nweb/data)]
    S --> M[web/ Leaflet haritası]
    S --> F[feed.xml RSS]
    S --> T[Telegram: konum iğnesi + Maps/MarineTraffic linkleri]
```

**Durum merdiveni** — çıktıyı bu yönetir:

| Kaynak | status | Haritada | Feed | Telegram |
| :-- | :-- | :-- | :-- | :-- |
| Yalnız AIS anomalisi | `signal` | soluk, kesik çizgili | evet | hayır |
| AIS + haber | `probable` | turuncu | evet | hayır |
| DSC distress | `probable` | turuncu | evet | hayır |
| Resmi açıklama | `confirmed` | kırmızı | evet | evet |
| Sonuç geldi | `resolved` / `false-positive` | yeşil / gri | evet | hayır |

Önleme kanalı ayrı hat: girdi zaten resmi (MGM/NAVTEX) → doğrudan iletilir.

---

## Hızlı başlangıç

```bash
git clone <repo>
cd maritime-watch
py -m pip install -r requirements.txt      # Windows: "py", Linux/mac: "python3"

py run.py --once --serve                   # bir döngü + http://127.0.0.1:8000
```

Anahtar olmadan AIS katmanı `src/ingest/samples/` içindeki örnek veriyle,
uyarılar önbelleğe alınmış örneklerle çalışır; Telegram mesajları konsola ve
`data/outbox.log`'a yazılır (gönderilmez).

### Canlı veri için (hepsi ücretsiz, kartsız)

1. `cp .env.example .env`
2. `AISSTREAM_KEY` — <https://aisstream.io/apikeys> (yalnız e-posta)
3. `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — Telegram'da `@BotFather` → `/newbot`
4. `py run.py --loop --send`

### Komutlar

| Komut | Ne yapar |
| :-- | :-- |
| `py run.py --once` | tek döngü (dry-run), çık |
| `py run.py --loop` | `config.yaml → loop.interval_seconds` aralığıyla sürekli |
| `py run.py --serve` | sadece `web/` klasörünü sun |
| `py run.py --once --send` | Telegram'a gerçekten gönder |
| `--no-ais` / `--no-scrape` | katman kapat |
| `py -m pytest` | testler (33) |

---

## Dağıtım

| Yol | Maliyet | Gecikme | Not |
| :-- | :-- | :-- | :-- |
| **GitHub Actions + Pages** (`.github/workflows/update.yml`) | $0 | ~15 dk | Sunucu yok. Public repo = sınırsız Actions dakikası. Secrets: `AISSTREAM_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Fly.io / Koyeb free | $0 | ~gerçek zamanlı | Küçük always-on; WebSocket'i açık tutar |
| Ucuz VPS (Hetzner ~€4/ay, RackNerd ~$1/ay) | düşük | gerçek zamanlı | `py run.py --loop --send` + systemd; SDR/DSC modülleri de buraya |

Harita statik — `web/` klasörünü herhangi bir statik host (GitHub Pages, Vercel,
Netlify, Cloudflare Pages) yayınlar.

---

## Hukuki tasarım

Bu araç **TCK 132** (haberleşmenin gizliliği) ve **KVKK** gözetilerek tasarlandı:

- **Yayına giden akış yalnızca resmi ve açık kaynaklıdır** — resmi açıklamalar,
  MGM/NAVTEX uyarıları, ve alım için yayınlanan açık veri (AIS, DSC güvenlik
  yayını). Bunları toplamak ve dağıtmak serbesttir.
- **Kişiler arası telsiz trafiği kaydedilmez, dökümü çıkarılmaz, yayınlanmaz.**
- `src/sdr/` modülü **opsiyonel, deneysel, varsayılan kapalı**. Kuralları:
  yalnız alıcı (RX-only), yalnız izinli frekanslar (Ch16, DSC, NAVTEX, amatör
  afet, havacılık acil — **asla** kolluk/askeri), kalıcı kayıt yok, ham
  yakalama asla yayınlanmaz. Ayrıntı: [`src/sdr/README.md`](src/sdr/README.md).
- Kişisel veri: harita ve feed yalnızca resmi açıklamada geçen bilgiyi gösterir;
  isim/tekne adı ancak resmi kaynak verdiyse yer alır.

Habercilik açısından: haber değeri taşıyan olguyu (bir kurtarma yaşandığı)
doğrulanmış, kaynak gösterilerek duyurmak korunur; ham telsiz trafiğini
dağıtmak değil.

---

## Depo yapısı

```text
run.py                    orkestratör (--once / --loop / --serve)
config.yaml               bölge, eşikler, anahtar kelimeler, aralıklar
src/
  config.py               config.yaml + .env
  model.py                Incident / Warning (CAP-benzeri)
  store.py                web/data/*.json + events.jsonl
  ingest/
    ais_stream.py         aisstream.io burst capture (+ örnek fallback)
    official.py           Sahil Güvenlik scrape (defensive + cached sample)
    openmeteo.py quakes.py navwarn.py news.py gdacs.py eonet.py reliefweb.py metar.py
    _net.py               ortak fetch + örnek fallback
    samples/              çevrimdışı test ve ilk çalıştırma için önbellek
  process/
    anomaly.py            kural tabanlı AIS anomali + SART/MOB + kalıcı gemi izi
    dedup.py              olay korelasyonu + same_hazard (çift uyarı birleştirme)
    classify.py           status / confidence / severity / geocode / en yakın liman
  render/
    feed.py               feed.xml (RSS)
    mapdata.py            summary.json
  alert/telegram.py       dry-run + gerçek gönderim, tekrar koruması
  sdr/                    opsiyonel modül — entegrasyon rehberi + stub
web/                      Leaflet haritası (statik, build yok)
tests/                    pytest (33)
.github/workflows/        tests.yml + update.yml (bedava dağıtım)
```

## Yol haritası

Bkz. [`TODO.md`](TODO.md).

## Katkı

Bkz. [`CONTRIBUTING.md`](CONTRIBUTING.md). Kullanılan/atıf yapılan açık kaynak
projeler: [`NOTICE`](NOTICE).

## Lisans

MIT — [`LICENSE`](LICENSE).
