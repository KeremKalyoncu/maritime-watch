# Güvenlik, Performans ve NFR — Honest Data Integrity

| Alan | Değer |
|------|--------|
| **Özellik** | `honest-data-integrity` |
| **Üst sınır** | Note 4 Open-Meteo yok · outlook ≪ 256 KB · az commit · fixture publish yok |

---

## 1. Güvenlik & yetkilendirme

- Yanlış emniyet = güvenlik olayı (integrity > confidentiality bu pakette).  
- Telegram HTML escape; web `esc()`.  
- Secrets commit edilmez.  
- RBAC yok (public read).

---

## 2. Performans

- Forecast bir cycle’da bir kez çekilip paylaşılır (çift Open-Meteo turu azaltılır).  
- Cache TTL 15 dk (mevcut).  
- Pagination/Redis yok.  
- Note 4: yalnız dosya okuma + poll.

---

## 3. Loglama

| Olay | Seviye |
|------|--------|
| coverage missing | INFO `[outlook] coverage present=N missing=…` |
| refuse sample | WARN (mevcut) |
| sahte skor path kaldırıldı | — (kod silinir) |
| parse error | print mevcut |
