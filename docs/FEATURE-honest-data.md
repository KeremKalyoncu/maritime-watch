# Feature Özeti ve Amaç — Dürüst Veri Bütünlüğü

| Alan | Değer |
|------|--------|
| **Özellik adı** | Honest Data Integrity |
| **Kod adı** | `honest-data-integrity` |
| **Durum** | Planlandı — uygulama öncesi Context & Scope |
| **Üst ilke** | *Saying nothing beats saying something false* |
| **Dağıtım kısıtı** | Az commit (hedef 2) · Note 4’te ekstra Open-Meteo yok · Actions cycle ağır işi yapsın |

---

## Feature taslağı (1–2 cümle)

Go/No-Go penceresi yayında ama kısmi tahmin, eksik dalga→yeşil saat ve skor yokken uydurma `85/100` gibi yollar hâlâ **yanlış emniyet** üretebiliyor. Bu özellik, `outlook` kapsamını tamamlar, eksik ölçümü `unknown` sayar, eski tahmini işaretler ve resmi MGM alarmını Bugün cevabının yanına koyar — uydurma skor/pencere yok.

---

## 1. Temel Problem ve Çözüm

### 1.1 Operasyonel problem

Balıkçı asıl cevabı (`/balikci`, web Bugün paneli) güvenerek kullanmalı. Bugün:

| Boşluk | Etki |
|--------|------|
| `outlook.json` bazen Marmara / Karadeniz’siz | Varsayılan bölge → “pencere yok”; ürün kırık görünür |
| `null` dalga/gust → `0` → `ok` | Eksik marine API yeşil pencere gibi okunur |
| `/neredeyim` skor yokken `85/100 Elverişli` | Doğrudan sahte yeşil |
| Actions gecikince taze sanılan pencere | Sessiz eski tahmin |
| MGM fırtına uyarısı ayrı kanalda | Model pencere ile resmi alarm yan yana değil |

### 1.2 Teknik problem

1. `render_outlook` partial `fetch_forecast_points` ile yazılabiliyor; marine fail → nokta tamamen atılıyor.
2. `level_for(None, None)` → `(0, 0)` → `ok`.
3. Bot fallback skoru sabit `85`.
4. Stale kontrolü web genel `#stale`’de var; outlook/`/balikci` özel değil.
5. `warnings.json` (MGM dahil) Bugün yüzeyine bağlanmamış.

### 1.3 Çözüm

- Outlook yazımını tam/partial-aware hale getir: coverage + eksik alan listesi; wind live ise marine yokken bile nokta yaz (saatler `unknown`).
- `unknown` seviye: eksik ölçüm asla `ok` sayılmaz.
- `/neredeyim`: skor yok → “skor yok / veri yok”.
- `generated` > `stale_hours` → bot + web “eski tahmin”.
- Seçili bölgeyle eşleşen MGM/aktif uyarıyı Bugün altında göster.
- Note 4: yalnız JSON okuma.

---

## 2. Kullanıcı Akışı (User Journey)

| Adım | Persona | Ne olur | Bitirme |
|------|---------|---------|---------|
| 1 | Balıkçı `/balikci` | Tam bölge listesi veya dürüst “bu bölge henüz yok”; varsa saatler | Yeşil uydurma yok |
| 2 | Eksik dalga saati | Gri `unknown` / “ölçüm yok” | Çıkış kararı skor uydurmaz |
| 3 | `/neredeyim` | Liman + varsa skor; yoksa net “skor yok” | Sahte 85 yok |
| 4 | Eski cycle | “⚠ Eski tahmin (~Nh)” üstte | Kullanıcı gecikmeyi görür |
| 5 | MGM fırtına | Bugün altında “Resmi: …” | Model + resmi aynı bakış |

---

## 3. Kapsam Dışı (Out of Scope)

- Yeni DB / Redis / framework / React rewrite  
- SDR / NAVTEX / sürekli AIS daemon  
- Yeni MGM marine endpoint avı (mevcut `mgm_alarms` yeter)  
- AIS hayalet sinyal prune turu (ayrı paket)  
- CPA radar kalibrasyonu, ML  
- Marketing README rewrite, WIP commit spam  

**Definition of Done:** Testler yeşil · sahte 85 yok · null≠ok · outlook coverage dürüst · stale + MGM satırı bot+web · 2 commit · Note 4 pull+restart.
