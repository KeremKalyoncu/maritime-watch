# API ve Entegrasyon Sözleşmesi — Honest Data Integrity

| Alan | Değer |
|------|--------|
| **Özellik** | `honest-data-integrity` |
| **API stili** | Static JSON GET + Telegram komut yüzeyi |
| **Base** | `https://keremkalyoncu.github.io/maritime-watch` |
| **İlgili** | Data Model · Architecture |

---

## API ihtiyacı

1. Web/bot → `GET .../data/outlook.json` (coverage + unknown seviyeler).  
2. Web/bot → `GET .../data/warnings.json` (MGM satırı için filtre).  
3. Bot → disk aynı dosyalar (Note 4).  
4. Open-Meteo wind isteğine `wind_direction_10m` eklenmesi (cycle only).

---

## 1. Endpoint & method

| Kaynak | Method | Path |
|--------|--------|------|
| Outlook | GET | `/data/outlook.json` |
| Warnings | GET | `/data/warnings.json` |
| Safety | GET | `/data/safety_index.json` |

Auth yok. Yazma yalnız Actions/`run.py --once`.

---

## 2. Request / validasyon

Okuma: body yok. Bot komutları değişmez (`/balikci`, `/neredeyim`, …).

Stale eşiği: `config.outlook.stale_hours` yoksa `alert.stale_hours` (default 2).

MGM eşleme: `warning.area` normalize ⊆ seçili deniz adı veya tersi (`Marmara` ↔ `Marmara Denizi`); `org`/`sources` içinde MGM veya headline deniz kelimesi.

---

## 3. Response & hatalar

| Durum | Davranış |
|-------|----------|
| 200 + dolu outlook | Pencereler + coverage |
| 200 + coverage.missing dolu | Yine 200; UI “şu bölgeler bu cycle’da yok” |
| Dosya yok / 404 | Bot: “henüz derlenmedi”; web: mevcut error state |
| `generated` eski | 200 + istemci stale bandı (HTTP 410 yok — static host) |
| Skor yok `/neredeyim` | Metin: skor yok; HTTP N/A |

Telegram HTML escape mevcut kurallarla.
