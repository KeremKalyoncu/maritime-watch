# Uygulama Görev Listesi — Honest Data Integrity

| Alan | Değer |
|------|--------|
| **Özellik** | `honest-data-integrity` |
| **Commit hedefi** | 2 (1 kod+test, 1 docs/roadmap) |

---

## Uygulanacak özet

Dürüst seviye + partial coverage + sahte skor öldürme + stale + MGM Bugün satırı.

---

## Görevler

### A — Process / ingest (zorunlu)
- [x] `window.level_for` / `UNKNOWN` / serialize null-safe  
- [x] `openmeteo` None-hizalı seriler; wind-only nokta; wind_dir  
- [x] `outlook.coverage`  
- [x] `run.py` shared fetch; outlook weather_grid ile aynı pts  

### B — Surfaces (zorunlu)
- [x] bot: neredeyim no-fake-score; stale; MGM; unknown satır  
- [x] web: stale + unknown CSS + MGM  
- [x] weather_grid: no invent-0; real dir  

### C — Test / ship
- [x] unit tests  
- [x] pytest yeşil  
- [ ] 2 commit · push · Note 4 pull+restart  

### Bilerek sonra
- AIS hayalet prune, eval corpus büyütme
