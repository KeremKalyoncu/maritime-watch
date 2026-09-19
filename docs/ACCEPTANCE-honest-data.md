# Kabul Kriterleri ve Test Senaryoları — Honest Data Integrity

| Alan | Değer |
|------|--------|
| **Özellik** | `honest-data-integrity` |
| **Koşum** | `pytest -q` · manuel `/balikci` · `/neredeyim` · web panel |

---

## Kabul (bitmiş hâl)

1. `level_for(None, None)` → `unknown`; `(10, None)` yalnız gust ile skorlanır; null→0 yok.  
2. Kısmi forecast → `coverage.missing` dolu; mevcut alanlar yazılır.  
3. `/neredeyim` skor yok → metinde `85` geçmez; “veri yok” veya eşdeğeri.  
4. Eski `generated` → bot/web stale uyarısı.  
5. Eşleşen MGM/uyarı → Bugün altında resmi satır (yoksa sessiz).  
6. Note 4 path Open-Meteo çağırmaz.  
7. `pytest` ilgili testler yeşil.

---

## Test senaryoları

| ID | Senaryo | Beklenen |
|----|---------|----------|
| T1 | unit level_for nulls | unknown / partial |
| T2 | render_outlook coverage | missing list |
| T3 | bot neredeyim no rating | no 85 |
| T4 | bot stale outlook | eski tahmin metni |
| T5 | bot/web unknown window | gösterilir, ok sanılmaz |
| T6 | regression mevcut ok/watch/danger | bozulmaz |

---

## Manuel smoke (prod)

1. `/start` menü  
2. `/balikci` Marmara (veya kayıtlı) — pencere veya dürüst missing  
3. Konum → `/neredeyim` — sahte skor yok  
4. Web Bugün paneli — gri unknown / stale / MGM varsa
