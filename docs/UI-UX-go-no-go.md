# UI/UX Davranış Planı — Go / No-Go Window Alignment

| Alan | Değer |
|------|--------|
| **Özellik** | `outlook-cache-surfaces` |
| **UI stack** | Vanilla HTML/CSS/JS · React/Vue **yok** · Toast kütüphanesi **yok** |
| **Tasarım ilkesi** | Mevcut harita kompozisyonuna ince şerit; kart/dashboard şişirmesi yok |
| **İlgili** | Feature · API Contract · Business Logic |

---

## Arayüz beklentisi (doldurulmuş)

Header’da, mevcut `#safety-strip` **hemen altında** (veya üstünde, tek blok gibi okunan) ince bir **“Bugün çıkılır mı?”** şeridi:

- Sol: etiket **Bugün** + bölge `<select>` + tekne sınıfı `<select>` (Küçük / Orta / Büyük).  
- Orta: yatay zaman dilimleri — yeşil `ok` · sarı `watch` · kırmızı `danger` (saat aralıkları: `08:00–15:00`).  
- Sağ: varsa `💡 En geç HH:MM limana dön`; yoksa satır gizli.  
- Alt satır (ikincil, soluk): **Şimdi** — aynı bölgenin safety skoru / `data_quality` uyarısı.  
- Harita, KPI, chip’ler, timeline **aynı kalır**; panel onları ezmez.

Mobil: select’ler tam genişlik; pencereler yatay scroll veya 2 satır wrap. Toast yok; geri bildirim mevcut `#stale` / `#offline-bar` / panel-içi mesaj kalıbı.

Telegram `/balikci` bu planın “ikinci yüzey”i — aynı bilgi hiyerarşisi (Bugün → Şimdi → disclaimer), DOM yok.

---

## 1. Bileşen hiyerarşisi

Vanilla JS’te “Smart / Dumb” = **veri sahibi fonksiyonlar** vs **saf DOM/render fonksiyonları**. Yeni framework bileşeni yok.

```
App (app.js bootstrap)                          « Smart — fetch, LAST, refresh 60s
├── OfflineBar (#offline-bar)                   « mevcut Presentational
├── Header
│   ├── Topbar / Ctrl                           « mevcut
│   ├── SafetyStrip (#safety-strip)             « Smart: straits+safety join → Dumb HTML
│   ├── OutlookPanel (#outlook-panel)           « YENİ Smart container
│   │   ├── OutlookControls                     « Dumb: 2× <select>
│   │   ├── OutlookTimeline                     « Dumb: window chips/segments
│   │   ├── OutlookReturnBy                     « Dumb: tek satır veya hidden
│   │   ├── OutlookNowSecondary                 « Dumb: skor satırı veya hidden
│   │   └── OutlookStatusMessage                « Dumb: loading/empty/error metin
│   ├── FilterRow / KPIs / StaleAlert           « mevcut
├── Map + Playback                              « mevcut
└── Side Timeline + #empty                      « mevcut empty kalıbı
```

### 1.1 Smart (Container)

| Birim | Sorumluluk | Tutmaz |
|-------|------------|--------|
| `loadOutlook()` | `GET data/outlook.json` → `LAST.outlook` | HTML string biriktirmez (mümkünse) |
| `getOutlookPanelState()` / `setOutlookPanelState()` | `{ boat, area }` | Persist zorunlu değil |
| `renderOutlookPanel()` | `LAST.outlook` + `LAST.safety` + panel state → child render çağrıları | Seviye hesabı yapmaz |
| `onOutlookControlChange` | select → state → re-render | Network yazmaz |

### 1.2 Dumb (Presentational)

| Birim | Girdi | Çıktı |
|-------|-------|--------|
| `htmlOutlookControls(boat, area, areaNames, labels)` | primitives | `<select>` markup |
| `htmlOutlookTimeline(windows, lang)` | `WindowSegment[]` | renkli segmentler |
| `htmlOutlookReturnBy(return_by, lang)` | `string \| null` | satır veya `""` |
| `htmlOutlookNow(rating \| null, lang)` | safety rating | soluk skor satırı |
| `htmlOutlookStatus(kind, lang)` | `loading\|empty\|error\|stale` | tek satır mesaj |

**Kural:** Dumb fonksiyonlar `fetch` / `LAST` okumaz; sadece argüman.

### 1.3 DOM mount (HTML)

```html
<section id="outlook-panel"
         class="outlook-panel"
         role="region"
         aria-label="Bugün denize çıkış penceresi"
         aria-live="polite">
  <!-- JS doldurur -->
</section>
```

Konum önerisi: `#safety-strip` sonrası, `.filter-row` öncesi — “önce karar, sonra olay filtresi”.

### 1.4 i18n

Mevcut `I.tr` / `I.en` sözlüğüne key’ler:

`outlook_title`, `outlook_today`, `outlook_now`, `outlook_boat`, `outlook_area`, `outlook_return`, `outlook_loading`, `outlook_empty`, `outlook_error`, `outlook_stale`, `boat_small`, `boat_medium`, `boat_large`, `level_ok`, `level_watch`, `level_danger`.

### 1.5 Telegram yüzey (UI değil, aynı hiyerarşi)

```
FishermanReport (smart: dosya oku + DTO)
└── metin blokları (dumb sırası): Bugün windows → return_by → Şimdi → disclaimer
```

---

## 2. Tüm UI durumları

Panel state machine:

```
idle → loading → success
              ↘ empty
              ↘ error
success → (refresh) loading → …
success + stale_flag → success_stale (içerik + uyarı)
offline + cache hit → success_cached
offline + no cache → error_offline
```

### 2.1 Idle

| Ne | Görünüm |
|----|---------|
| İlk paint, fetch başlamadan | Panel yer kaplar; kısa placeholder veya hemen `loading` (tercih: **doğrudan loading** — idle flash yok) |
| Davranış | `aria-busy="true"` loading’de |

### 2.2 Loading

| Ne | Görünüm |
|----|---------|
| İlk yükleme / 60s refresh | Skeleton: 2 select disabled + 3 gri pill (`outlook-skel`) — **spinner zorunlu değil** (mevcut site sade) |
| Süre | `getJSON` dönene kadar; max pratik ~3–5s sonra error |
| Eski başarı varken refresh | **İçeriği silme** — soft refresh: opacity 0.7 veya köşede küçük “güncelleniyor” (opsiyonel). Tercih: stale içeriği tut, arka planda değiştir (flicker yok) |

### 2.3 Success

| Ne | Görünüm |
|----|---------|
| `classes[boat].areas` dolu, seçili area bulunur | Controls aktif · timeline renkli · return_by varsa sağ/alt |
| Şimdi satırı | Aynı `area` safety rating varsa; `data_quality=unknown` ise skor yanında “ölçüm eksik” |
| Davranış | Select değişince anında re-render (local; network yok) |
| A11y | `aria-live="polite"` region güncellenir; renk yalnız bırakılmaz (saat + level metin) |

**Renk anlamı (mevcut palete uy):**

| Level | Anlam | Metin |
|-------|--------|------|
| ok | Uygun | TR: Uygun / EN: OK |
| watch | Dikkat | TR: Dikkat / EN: Caution |
| danger | Çıkma | TR: Çıkma / EN: Stay in |

### 2.4 Empty

| Tetikleyici | Görünüm |
|-------------|---------|
| `200` + `areas.length === 0` | Timeline gizli; `OutlookStatusMessage`: “Bugün için pencere üretilemedi (tahmin yok).” |
| Area select’te isim yok | Area listesi safety/outlook birleşiminden; boşsa tek disabled option |
| `return_by` null + worst ok | Return satırı gizli; timeline tümü yeşil olabilir — empty değil, success |

Empty ≠ Error. Kullanıcıya “bir şey bozuldu” deme.

### 2.5 Error

| Tetikleyici | Görünüm |
|-------------|---------|
| `404` / network / JSON parse | Panel içinde sakin uyarı (kırmızı banner değilse mevcut `#stale` tonu): “Çıkış penceresi henüz derlenmedi.” |
| Harita | Çalışmaya devam (incidents bağımsız) |
| Retry | Sonraki 60s `refresh` otomatik; manuel buton **zorunlu değil** (az UI) |

### 2.6 Stale / Offline (mevcut sistemle birleşik)

| Durum | Görünüm |
|-------|---------|
| `summary.stale_hours` aşımı | Mevcut `#stale` — panel ekstra kırmızıya boyanmaz; isteğe bağlı ince “veri HH:MM UTC” |
| `navigator.onLine === false` | Mevcut `#offline-bar`; panel SW cache’ten doluysa success_cached |
| SW `offline: true` JSON | Error/empty mesajı; uydurma pencere yok |

### 2.7 Durum × ekran özeti

| State | Controls | Timeline | Return | Now | Status msg |
|-------|----------|----------|--------|-----|------------|
| Loading (cold) | disabled skel | skel pills | hidden | hidden | optional |
| Loading (warm) | enabled | previous | previous | previous | none/soft |
| Success | on | on | if set | if rating | hidden |
| Empty | on (areas may be empty) | hidden | hidden | optional | empty copy |
| Error | disabled or on+empty | hidden | hidden | hidden | error copy |

---

## 3. Kullanıcı geri bildirimleri

### 3.1 Toast mesajları

**Bu feature’da toast yok.**

Gerekçe: site zaten `#offline-bar` + `#stale` + timeline `#empty` kullanıyor; yeni toast kütüphanesi / stack gürültüsü Note 4 ve PWA kapsamı dışı. Geri bildirim = **panel-içi status** + mevcut global bar’lar.

| Olay | Geri bildirim |
|------|----------------|
| Outlook yüklenemedi | Panel status (error) |
| Offline | `#offline-bar` |
| Stale cycle | `#stale` |
| Select değişti | Anında timeline (toast yok) |

### 3.2 Form hata uyarıları

Form submit yok. “Form” = iki `<select>`.

| Durum | Davranış |
|-------|----------|
| Geçersiz boat (hacked DOM) | Coerce `small`; sessiz |
| Area listede yok | İlk area’ya düş; status yok |
| Zorunlu alan boş | Select’ler her zaman bir value tutar (initial state) — HTML5 `required` opsiyonel |

Kırmızı input border / tooltip **gerekmez**.

### 3.3 Optimistic updates

| Senaryo | Karar |
|---------|--------|
| Select boat/area | **Local optimistic UI** — sunucuya yazma yok; state hemen, render hemen. Bu “optimistic network write” değil. |
| POST/PUT outlook | Yok — optimistic write **yok** |
| Telegram `/balikci` | Optimistic yok; dosya oku → cevap |
| 60s refresh | Warm cache: eski UI kalır, yeni gelince swap (rollback = eskiyi gösterme devam; fail olursa eski kalır) |

### 3.4 Mikro-etkileşim (hafif)

- Segment hover: `title="{start}–{end} · {gust} kn · {wave} m"`.  
- Return_by: vurgulu ama sticker/badge değil.  
- Motion: mevcut siteye uyum — max 1 kısa fade (opsiyonel); zorunlu animasyon yok.  

### 3.5 Telegram geri bildirimi

| Durum | Mesaj tipi |
|-------|------------|
| Success | Bugün + opsiyonel Şimdi |
| Empty areas | “Tahmin alınamadı / pencere yok” |
| File missing | “Henüz derlenmedi” |
| Parse error | Kısa ⚠️ — stack yok |

Typing indicator / toast yok.

---

## 4. Responsive & erişilebilirlik checklist

| Madde | Beklenti |
|-------|----------|
| Genişlik &lt; 640px | Select’ler stack; timeline `overflow-x: auto` |
| Kontrast | Level renkleri + metin etiketi |
| Klavye | Select tab ile; panel `role="region"` |
| `prefers-reduced-motion` | Fade kapat |
| Harita odağı | Panel harita `tabindex` savaşını bozmaz |

---

## 5. Bilinçli UI dışı / yapılmayacaklar

- Modal “outlook wizard”  
- Ayrı sayfa `/outlook.html` (zorunlu değil)  
- Skor’u hero’da pencereden büyük göstermek  
- Floating badge / promo chip (kullanıcı design kuralı)  
- Toast / snackbar kütüphanesi  
- Optimistic yazma / undo  
- localStorage zorunluluğu (sonraki milestone)  

---

## 6. Uygulama sırası (UI)

1. `index.html` mount + `style.css` `.outlook-panel`  
2. Dumb HTML helpers + i18n keys  
3. Smart load/render + `LAST.outlook`  
4. Safety “Şimdi” soft-join  
5. Loading/empty/error status  
6. Manuel mobil kontrol  

---

*UI başarısı: balıkçı 3 saniyede “bugün saat kaça kadar”ı okur; harita ikincil kalır.*
