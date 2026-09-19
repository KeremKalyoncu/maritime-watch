# Feature Özeti ve Amaç — Go / No-Go Pencere Hizalaması

| Alan | Değer |
|------|--------|
| **Özellik adı** | Go / No-Go Window Alignment |
| **Kod adı** | `outlook-cache-surfaces` |
| **Durum** | Planlandı — uygulama öncesi Context & Scope |
| **İlgili motor** | `src/process/window.py` (mevcut) |
| **Dağıtım kısıtı** | Az commit (hedef 2) · Note 4 bot host’u hafif kalsın · Actions cycle ağır işi yapsın |

---

## Feature taslağı (1–2 cümle)

Küçük tekne sahibine verilen asıl cevap — **“bugün çıkabilir miyim, saat kaça kadar?”** — şu an yalnızca Telegram sabah outlook / `/durum` yolunda tutarlı; web haritası ve `/balikci` anlık güvenlik skoruna kayıyor. Bu özellik, mevcut `window.py` motorunu cycle’da bir kez hesaplayıp `outlook.json` olarak önbelleğe alarak **web, bot ve sabah mesajını aynı saatlik pencere diline hizalar**; Note 4 üzerinde ekstra hava API çağrısı yapmaz.

---

## 1. Temel Problem ve Çözüm

### 1.1 Operasyonel problem

Maritime Watch’un ürün vaadi tek cümledir: tekne boyuna göre **saatlik çıkış / dönüş penceresi**. Balıkçı veya amatör denizci sabah kararını “skor 82/100” ile değil, şu dil ile verir:

> Marmara · küçük tekne · 08:00–15:00 uygun · 15:00’ten sonra çıkma · limana en geç 14:30 dön.

Bugün bu dil:

| Yüzey | Ne görüyor | Sorun |
|--------|------------|--------|
| Sabah Telegram outlook | Saatlik pencere (`window.py`) | Doğru ürün |
| `/durum` / abone outlook | Saatlik pencere (çoğu zaman canlı fetch) | Doğru, ama Note 4’te pahalı olabilir |
| `/balikci` | `safety_index` anlık skoru | Vaadi yanlış karşılıyor |
| Web haritası | Skor şeridi + olay/CPA | Asıl soruya cevap yok |
| README / pazarlama | Saat penceresi anlatıyor | Gerçek UX ile drift |

Sonuç: kullanıcı “ürünü denedim, yine genel hava skoru” hissine kapılır; güven ve dönüşüm (star / abone / tekrar kullanım) ana vaatten kopar. Ayrıca `/kazalar` üretim JSON şekliyle uyumsuz olduğu için istihbarat yolunda kırık bir komut kalır — ikincil ama güven zedeleyen bir operasyonel kusur.

### 1.2 Teknik problem

1. **Çift cevap mimarisi:** `safety_index` (anlık 0–100) ile `window` (saatlik ok/watch/danger) aynı “çıkılır mı?” sorusuna bağlanmış; kod yolları birleşik değil.
2. **Tekrarlayan ağır iş:** Bot tarafında outlook metni gerektiğinde Open-Meteo’yu yeniden çekebiliyor. Edge host (Galaxy Note 4 / Termux) için bu gereksiz CPU, TLS ve batarya yükü.
3. **Yayımlanmayan ara ürün:** Cycle zaten marine+wind serisini çekiyor; pencere çıktısı kalıcı bir `web/data` artifact’ına yazılmıyor — web tüketicisi yok.
4. **CPA gürültüsü + null alanlar:** Aynı MMSI CPA ve eksik dalga/SST ile “100 skor” güveni zedeler; ana vaat olmasa da karar destek yüzeyinin yanına gölge düşürür.

### 1.3 Çözüm (bu feature’ın yaptığı iş)

- Her pipeline cycle’ında (tercihen GitHub Actions `--once`) Open-Meteo noktalarından **üç tekne sınıfı** için `window.build` çalıştırılır.
- Sonuç `web/data/outlook.json` olarak yazılır (Pages + bot’un okuyacağı tek kaynak).
- `/balikci` ve web “Bugün” şeridi **bu dosyadan** okur; skor varsa ikinci satır / “anlık” etiketiyle kalır.
- Outlook metnine **“limana dönüş en geç HH:MM”** türetilir (`first_danger` / ilk ciddi `watch` sınırı).
- `/kazalar` hem dizi hem `{incidents:[]}` şeklini kabul eder; varsayılan confirmed+probable.
- CPA: `mmsi1 == mmsi2` elenir; eşleşmeden önce MMSI başına tek pozisyon.
- Safety: eksik kritik ölçümlerde kör “100 / elverişli” basılmaz; dil olarak **şimdi (skor)** vs **bugün (pencere)** ayrılır.

**Bilerek yapılmayan büyük sıçrama:** Yeni veritabanı, sürekli AIS daemon, SDR, framework rewrite yok. Mevcut motor + bir JSON artifact + yüzey hizası.

---

## 2. Kullanıcı Akışı (User Journey)

### Persona A — Küçük tekne / balıkçı (birincil)

| Adım | An | Ne olur | Bitirme koşulu |
|------|-----|---------|----------------|
| 0 | Önkoşul | Actions cycle `outlook.json` + `safety_index.json` üretmiş; bot Note 4’te poll ediyor | Artifact taze (`generated` makul) |
| 1 | Sabah uyanır | 06:00 civarı (veya abone ayarı) kişiselleştirilmiş outlook: bölgeler + tekne sınıfı + saat blokları + dönüş tavsiyesi | Mesajda saat aralığı var |
| 2a | Telefonda kontrol | `/balikci marmara` (veya kayıtlı bölge) → **Bugün:** yeşil/sarı/kırmızı saatler + “en geç HH:MM dön” → altta isteğe bağlı **Şimdi:** skor / dalga / rüzgâr | Saat penceresi skorun üstünde |
| 2b | Tarayıcıda kontrol | Harita açılır → hero’da “Bugün çıkılır mı?”: bölge + tekne sınıfı seçer → aynı pencere dili | Web’de de saat görünür |
| 3 | Karar | Limandan çıkış / erteleme / erken dönüş planı | Ürün işi bitti |
| 4 | İsteğe bağlı | `/mayday`, acil rehber, olay filtresi — ana karar sonrası | Bu feature’ın başarı kriteri değil |

### Persona B — Amatör denizci (seyirde)

| Adım | An | Ne olur |
|------|-----|---------|
| 1 | `/neredeyim` + GPS | En yakın liman + anlık koşullar (mevcut) |
| 2 | “Bugün kalan pencere?” | `/balikci` veya web sınıf seçimi → kalan saatler `outlook.json`’dan |
| 3 | Güven | Metin “model tahminidir” disclaimer’ı ile biter; 158/MGM teyidi hatırlatılır |

### Persona C — Gazeteci / istihbarat (ikincil, yan düzeltme)

| Adım | An | Ne olur |
|------|-----|---------|
| 1 | `/kazalar` veya haritada “Doğrulandı” | Kırık JSON okuma düzelmiş; confirmed/probable listelenir |
| 2 | RSS / harita | Mevcut davranış; bu feature yeni olay detay sayfası eklemez |

### Sistem akışı (kullanıcı görmez)

```
Actions: ingest Open-Meteo → window.build × {small,medium,large} × areas
       → write web/data/outlook.json
       → (mevcut) safety_index, map, RSS …
Pages:  statik dosyalar
Note4:  Bot poll → oku outlook.json / incidents.json → cevapla
        (Open-Meteo’ya komut başına gitme)
```

---

## 3. Kapsam Dışı (Out of Scope)

Bu aşamada **kesinlikle yapılmayacak** olanlar — hallucination, scope creep ve Note 4 / commit gürültüsünü önlemek için:

### Ürün / özellik

- [ ] SDR, Whisper, DSC, NAVTEX donanım entegrasyonu  
- [ ] Yeni “canlı VTS” veya sürekli AIS WebSocket daemon (Note 4 / cron modelini bozar)  
- [ ] Öğrenilmiş trafik / ML rota sapması modeli  
- [ ] Per-incident detay sayfası, AIS track playback UI genişletmesi  
- [ ] `regions.geojson` harita çizimi (ayrı iş)  
- [ ] Yeni NAVAREA / ReliefWeb / MGM marine endpoint avı veya kapalı kaynakları zorla açma  
- [ ] Çoklu dil UI redesign’i, React/Vue geçişi, PWA’nın baştan yazılması  
- [ ] Kullanıcı hesabı, ödeme, push native app, e-posta bülteni  
- [ ] Resmi kurtarma / DSC relay iddiası veya “ilk duyan biz” garantisi metinleri  

### Teknik / altyapı

- [ ] Veritabanı (Postgres/SQLite) veya Redis  
- [ ] Yeni mikroservis, kuyruk, container orchestration  
- [ ] Note 4’te ek cron ile ağır ingest (ingest Actions’ta kalsın)  
- [ ] Her bot komutunda canlı Open-Meteo (cache yoksa bile production path’te yasak say)  
- [ ] CPA eşiklerini “mükemmel navigasyon radarı” seviyesine kalibre etme turu (yalnız self-MMSI / dedupe hijyeni)  
- [ ] Parent klasör pazarlama dosyalarının (`linkedin.md` vb.) bu feature commit’ine karıştırılması  

### Süreç

- [ ] Çok sayıda küçük GitHub commit / WIP push  
- [ ] “İyileştirme” adı altında README’nin baştan yazılması (yalnız vaad↔gerçek drift düzeltmesi)  
- [ ] `src/sdr/` stub’ını silmek veya hukuki dokümanı yeniden tartışmak  

### Bilinçli erteleme (sonraki milestone)

- VPS’e geçince bot+ingest birleşik `--loop`  
- Eval corpus büyütme / confidence kalibrasyonu  
- Awesome list / büyüme işleri (ürün hizasından ayrı)

---

## Başarı kriterleri (Definition of Done)

1. `web/data/outlook.json` cycle sonunda üretiliyor; 3 tekne sınıfı + bölgeler + `generated` damgası var.  
2. Web hero’dan sınıf+bölge seçilince saatlik ok/watch/danger pencereleri görünüyor.  
3. `/balikci` önce pencereleri, sonra isteğe bağlı anlık skoru gösteriyor; “en geç HH:MM” satırı var.  
4. `/kazalar` canlı `incidents.json` (dizi) ile dolu/confirmed liste döndürüyor.  
5. CPA self-pair üretimde oluşmuyor (test + hijyen).  
6. Note 4 bot path’i komutta Open-Meteo çağırmıyor (cache okuma).  
7. En fazla **2** anlamlı commit; mesajlar *why* odaklı.  
8. Mevcut offline testler yeşil; outlook/bot/cpa için regresyon testleri güncel.

---

## Önerilen commit paketleri

1. **`fix: align go/no-go windows across bot, web, and outlook cache`**  
   Render + bot + web + CPA/kazalar + testler + kısa README drift düzeltmesi.  
2. **`chore: tidy docs drift and redundant noise`**  
   TODO/README tutarlılığı, gereksiz gürültü temizliği (feature kodundan ayrı, ince).

---

## Riskler ve hafifletme

| Risk | Hafifletme |
|------|------------|
| `outlook.json` şişer | Yalnızca pencere özeti (saat, level, max gust/wave); ham saatlik seri yok |
| Actions süresi artar | Aynı Open-Meteo serisi; ek maliyet yalnızca CPU’da `build` × sınıf |
| Eski bot cache’siz kalır | Fallback: dosya yoksa nazik “veri henüz yok” (canlı fetch yok) |
| Skor/pencere hâlâ karışır | UI/metin etiketleri: **Şimdi** / **Bugün** zorunlu |

---

*Bu doküman uygulama öncesi Context & Scope kilididir. Kapsam dışı listeye giren işler ayrı feature isteği olmadan açılmaz.*

**İlgili:** Mimari → [`ARCHITECTURE-MAP-go-no-go.md`](ARCHITECTURE-MAP-go-no-go.md) · Veri → [`DATA-MODEL-go-no-go.md`](DATA-MODEL-go-no-go.md) · API → [`API-CONTRACT-go-no-go.md`](API-CONTRACT-go-no-go.md) · İş mantığı → [`BUSINESS-LOGIC-go-no-go.md`](BUSINESS-LOGIC-go-no-go.md) · UI/UX → [`UI-UX-go-no-go.md`](UI-UX-go-no-go.md) · NFR → [`NFR-go-no-go.md`](NFR-go-no-go.md) · Görev listesi → [`TASK-LIST-go-no-go.md`](TASK-LIST-go-no-go.md) · Kabul → [`ACCEPTANCE-go-no-go.md`](ACCEPTANCE-go-no-go.md)
