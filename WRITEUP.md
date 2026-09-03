# Maritime Watch — proje yazısı (LinkedIn / blog taslağı)

## Kısa

Türkiye karasuları için deniz olaylarını erken görmeyi ve denizcilik hava
uyarılarını tek yerde toplamayı amaçlayan açık kaynak bir araç yaptım. AIS
anomalilerini, Sahil Güvenlik / AFAD açıklamalarını ve Meteoroloji Genel
Müdürlüğü deniz uyarılarını birleştiriyor; sonucu bir haritada, bir RSS
beslemesinde ve isteğe bağlı bir Telegram kanalında yayınlıyor.

**Donanım gerektirmez.** AIS verisi `aisstream.io`'nun ücretsiz WebSocket API'sinden
geliyor; resmi uyarılar scrape ediliyor. İsteyen daha sonra bir SDR alıcısı
ekleyip DSC (dijital tehlike çağrısı) ve NAVTEX modüllerini bağlayabilir —
entegrasyon rehberi repo'da.

## Neden

- Batmakta olan bir tekne için resmi kurtarma zinciri (Sahil Güvenlik MRCC, DSC,
  Cospas-Sarsat) zaten çalışıyor; üçüncü bir dinleyici buna bir şey katmaz.
- Değer **önlemede** ve **şeffaflıkta**: balıkçının fırtına uyarısını kaçırmaması,
  ve bir olayın ne zaman/nerede olduğunun kaynak gösterilerek tek yerde
  görünmesi (gazeteci, araştırmacı, aile için).

## Teknik

- **Dil/altyapı:** Python 3, 5 çalışma-zamanı bağımlılığı, gerisi standart kütüphane.
- **AIS anomali:** kural tabanlı, açıklanabilir — `not under command` / `aground`
  nav-status, seyir hızından ani duruş, ani rota değişimi, seyir halindeyken AIS
  sinyal kaybı. Gemi izleri döngüler arası kalıcı (`data/vessels.json`).
- **Füzyon:** olaylar konum + zaman penceresiyle korele ediliyor; her olayın bir
  `status` (signal → probable → confirmed) ve `confidence` değeri var. Harita
  doğrulanmamış sinyalleri açıkça "doğrulanmadı" etiketliyor.
- **Çıktı:** statik Leaflet + OpenSeaMap haritası (build adımı yok), RSS `feed.xml`,
  tekrar-korumalı Telegram bildirimi (varsayılan dry-run).
- **Test:** 33 çevrimdışı pytest; scraper'lar ağ yokken önbelleğe alınmış
  örneklere düşüyor.
- **Dağıtım:** GitHub Actions cron + Pages ile sıfır maliyet, sunucu yok
  (~15 dk gecikme); ya da küçük bir VPS'te `--loop`.

## Hukuki tasarım (bilerek öne çıkarıyorum)

TCK 132 (haberleşmenin gizliliği) ve KVKK ilk günden gözetildi:

- Yayına giden akış **yalnızca resmi ve açık kaynaklı** — resmi açıklamalar,
  MGM/NAVTEX uyarıları, alım için yayınlanan açık veri (AIS, DSC güvenlik yayını).
- Kişiler arası telsiz trafiği **kaydedilmez, dökümü çıkarılmaz, yayınlanmaz**.
- Opsiyonel SDR modülü varsayılan kapalı; yalnız alıcı, yalnız izinli frekanslar,
  kalıcı kayıt yok, ham yakalama asla yayınlanmaz.
- DSC tercih ediliyor çünkü yapısal (MMSI + konum + tehlike tipi) — gürültülü FM
  sesinde Whisper'dan hem daha isabetli hem hukuken daha savunulabilir.

## Sınırlar (dürüst)

- Kurtarma yapmaz.
- AIS'i olmayan tekneleri (Ege'deki göçmen botlarının çoğu) göremez.
- "İlk duyan biz" garantisi yok; resmi teyit beklendiği için erken-tespitin
  kamuya açık değeri sınırlı — asıl faydası bir haber merkezine özel ipucu ve
  önleme kanalı.

## Bağlantılar

- Kod: `<repo url>`
- Canlı harita: `<pages url>`
- Katkı: `CONTRIBUTING.md`

## SDR / eval eklenirse buraya

- whisper.cpp `ggml-small`, `-l tr` — Pi 4 vs i5 latency tablosu
- Simüle distress korpusunda WER + anahtar kelime recall/precision
- AIS anomali kurallarının sentetik sette precision/recall değeri
