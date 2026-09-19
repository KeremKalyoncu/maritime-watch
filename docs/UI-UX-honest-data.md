# UI/UX Davranış Planı — Honest Data Integrity

| Alan | Değer |
|------|--------|
| **Özellik** | `honest-data-integrity` |
| **UI** | Vanilla panel + Telegram metin; kart/dashboard yok |
| **İlgili** | Feature · Business Logic |

---

## Arayüz beklentisi

Bugün paneli / `/balikci` üstünde (gerektiğinde):

1. **Stale bandı** — soluk uyarı: `⚠ Eski tahmin (~2s)`  
2. **Timeline** — `ok` yeşil · `watch` sarı · `danger` kırmızı · **`unknown` gri** (“ölçüm yok”)  
3. **MGM satırı** — timeline altında: `📢 Resmi: {headline}` (max 2)  
4. **Coverage** — seçili bölge missing ise: “Bu cycle’da tahmin gelmedi” (uydurma saat yok)

`/neredeyim`: skor yoksa `🌊 Sefer skoru: veri yok (henüz derlenmedi)` — asla 85.

---

## 1. Bileşen hiyerarşisi

| Parça | Rol |
|-------|-----|
| `renderOutlookPanel` | Smart: LAST.outlook + warnings + safety |
| Timeline segments | Dumb: level class |
| Stale / MGM satırları | Presentational satırlar |
| Bot `_fisherman_text` / `_handle_location` | Metin eşleniği |

---

## 2. UI durumları

| State | Görünüm |
|-------|---------|
| Loading | Mevcut skeleton |
| Success taze | Timeline + opsiyonel MGM |
| Success stale | Stale bandı + timeline |
| Empty / missing area | Dürüst empty metin |
| Error dosya yok | Mevcut error |
| Unknown saat | Gri segment |

---

## 3. Geri bildirim

Toast yok. Telegram: tek/çift mesaj metin. Optimistic update yok (statik veri).
