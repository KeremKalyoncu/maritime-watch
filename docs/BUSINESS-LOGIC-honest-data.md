# İş Mantığı ve Edge Case Analizi — Honest Data Integrity

| Alan | Değer |
|------|--------|
| **Özellik** | `honest-data-integrity` |
| **Üst ilke** | Saying nothing beats saying something false |
| **İlgili** | Feature · Data Model · API |

---

## 1. Çekirdek iş mantığı

1. **level_for(g, w, limits)**  
   - ikisi de `None` → `unknown`  
   - yalnızca gust → dalga eşiği yok sayılır  
   - yalnızca wave → gust eşiği yok sayılır  
   - asla `None → 0.0` ile sakin varsayma  

2. **Nokta dahil etme (forecast)**  
   - Wind live + times dolu → dahil et  
   - Marine down → `waves = [null…]` hizalı; saatler çoğunlukla gust’a veya unknown’a düşer  
   - Wind down → nokta **atlanır** (coverage.missing)  

3. **coverage**  
   - `expected = len(config.points)`  
   - `present = len(areas in any class)`  
   - `missing = expected names − present`  

4. **Stale**  
   - `age_h = (now - generated)`; `age_h > stale_hours` → uyarı metni; pencereler yine gösterilir (silinmez)  

5. **Skor yok**  
   - `/neredeyim` ve benzeri: uydurma skor yasak  

6. **MGM satırı**  
   - Aktif uyarılar; alan eşleşmesi; en fazla 2 başlık; “Resmi MGM/uyarı” etiketi  

---

## 2. Edge case’ler

| Case | Davranış |
|------|----------|
| Tüm noktalar fail | outlook yazma skip (mevcut) veya coverage present=0 + skip |
| Kısmi 8/13 | Yaz; missing listelenir |
| Unknown-only gün | `worst=unknown`; return_by=null |
| Eski + MGM var | İkisi de gösterilir |
| warnings.json yok | MGM satırı sessizce yok |
| Concurrent cycle | Atomik tmp→replace (mevcut) |

---

## 3. Hata & ağ

| Olay | Fallback |
|------|----------|
| Open-Meteo timeout tek nokta | O nokta missing; diğerleri yazılır |
| Sample mode | Outlook refuse (mevcut) |
| Bot parse hata | “okunamadı”; yeşil uydurma yok |
| Note 4 offline Pages | Disk kopyası; yoksa dürüst mesaj |
