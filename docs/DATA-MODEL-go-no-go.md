# Veri Modeli ve Tipler — Go / No-Go Window Alignment

| Alan | Değer |
|------|--------|
| **Özellik** | `outlook-cache-surfaces` |
| **Kalıcılık** | İlişkisel DB **yok** — sözleşme = `web/data/*.json` (+ bot abone JSON) |
| **Tip dili** | Domain: Python 3.11+ · UI sözleşmesi: TypeScript-şekilli interface (vanilla JS’de JSDoc ile uygulanır) |
| **İlgili** | `FEATURE-go-no-go-alignment.md` · `ARCHITECTURE-MAP-go-no-go.md` |

---

## İlgili veri / nesne bilgisi (doldurulmuş)

| Nesne | Nerede yaşar | Bu feature’daki rol |
|-------|--------------|---------------------|
| Saatlik Go/No-Go pencereleri | **Yeni** `web/data/outlook.json` | Asıl ürün cevabı (**Bugün**) |
| Anlık güvenlik skoru | `web/data/safety_index.json` | İkincil (**Şimdi**); null-güven alanı |
| Olay listesi | `web/data/incidents.json` | `/kazalar` okuma şekli (dizi \| sarmalayıcı) |
| Tekne sınıfı eşikleri | `config.yaml` → `outlook.classes` | Domain limit kaynağı |
| Abone tercihleri | `data/bot_subscribers.json` | `boat`, `areas` (gitignore; host’ta) |
| Mevcut domain | `src/process/window.py` `Window` / `AreaOutlook` | JSON’a serileştirilir |

Ham Open-Meteo saatlik seri **persist edilmez** (şişme yok); yalnızca birleştirilmiş pencereler yazılır.

---

## 1. Veritabanı / şema değişiklikleri

### 1.1 Karar

| Konu | Karar |
|------|--------|
| Yeni tablo / kolon / FK / index | **Yok** |
| Migration aracı (Alembic vb.) | **Yok** |
| Kalıcılık modeli | Append/overwrite JSON artifact (Pages + gitignore politikası) |

İlişkisel karşılık gerekirse (ileride VPS + DB): `outlook_snapshots(id, generated_at, boat_class, area, payload jsonb)` — **bu feature kapsamında değil**.

### 1.2 Dosya-şema “migration” taslağı (v1)

Sürüm alanı ile geriye uyum:

```text
outlook.json          schema_version: 1   (YENİ dosya)
safety_index.json     schema_version: 1   (opsiyonel alan ekleri; eski okuyucular ignore eder)
incidents.json        şema değişmez; okuyucu toleransı artar
```

**Pseudo-migration (dokümantasyon; çalıştırılacak SQL yok):**

```
-- M001_create_outlook_artifact (logical)
UPSERT artifact web/data/outlook.json
  WITH schema_version = 1
  KEYS: generated, hours, tz_offset_hours, classes

-- M002_safety_index_additive (logical, non-breaking)
ALTER safety_index.json
  ADD OPTIONAL schema_version = 1
  ADD OPTIONAL meta.question = "now"
  ADD OPTIONAL ratings[].data_quality = "ok" | "partial" | "unknown"
  ADD OPTIONAL ratings[].baseline_boat_class = "small"

-- M003_incidents_reader_compat (code-only)
READER accepts:
  Incident[]  OR  { "incidents": Incident[], "generated"?: string }
WRITER continues to emit Incident[] (mevcut store davranışı)
```

### 1.3 Mantıksal ilişkiler (JSON içinde)

```
OutlookFile 1 ──N BoatClassOutlook   (keys: small|medium|large)
BoatClassOutlook 1 ──N AreaOutlook
AreaOutlook 1 ──N WindowSegment

SafetyIndexFile 1 ──N MarineSafetyRating   (area adı ile Outlook area’ya soft-join; FK yok)

Subscriber N ── (boat_class, areas[]) ── okur → BoatClassOutlook
```

- **1–N:** sınıf → bölgeler → pencereler (tek dosyada gömülü).  
- **N–N:** yok (junction table yok).  
- **Index:** dosya içi lookup = `classes[boat].areas.find(a => a.name === area)`; B-tree yok.

### 1.4 `.gitignore` / yayın

```
web/data/outlook.json    # generated each cycle (safety_index ile aynı politika)
```

Seed commit zorunlu değil; ilk Actions koşusu üretir.

---

## 2. Type / Interface tanımları

Aşağıdaki TypeScript blokları **sözleşme**; runtime’da Python `TypedDict` / `dataclass` + JS JSDoc ile karşılanır. Enum değerleri string literal (JSON-friendly).

### 2.1 Ortak skalalar (Domain enums)

```typescript
/** Go/No-Go seviyesı — window.py OK|WATCH|DANGER ile birebir */
export type WindowLevel = "ok" | "watch" | "danger";

/** Anlık skor bandı — safety_index.status */
export type SafetyStatus = "good" | "caution" | "danger";

/** Tekne sınıfı — config outlook.classes keys */
export type BoatClassId = "small" | "medium" | "large";

/** Ölçüm güveni — null dalga/SST için */
export type DataQuality = "ok" | "partial" | "unknown";

/** Yerel saat "HH:MM" veya gün sonu "24:00" */
export type LocalHHMM = string; // /^\d{2}:\d{2}$/

/** UTC ISO-8601 Z */
export type IsoDateTime = string; // e.g. 2026-09-19T05:02:34Z
```

### 2.2 Domain tipleri (Python ↔ TS)

Mevcut `window.py` ile hizalı:

```typescript
/** src/process/window.py :: Window */
export interface WindowSegment {
  start: LocalHHMM;   // inclusive
  end: LocalHHMM;     // exclusive (Open-Meteo slot sonu)
  level: WindowLevel;
  gust_kn: number;
  wave_m: number;
}

/** src/process/window.py :: AreaOutlook (+ serileştirme alanları) */
export interface AreaOutlook {
  name: string;
  lat: number | null;
  lon: number | null;
  windows: WindowSegment[];
  max_gust: number;
  max_wave: number;
  /** Türetilmiş — DANGER yoksa null */
  first_danger_start: LocalHHMM | null;
  /** Türetilmiş — limana dönüş tavsiyesi; yoksa null */
  return_by: LocalHHMM | null;
  /** Area içi en kötü seviye */
  worst: WindowLevel;
}
```

Python karşılık (uygulamada eklenecek / mevcut genişletme):

```python
# Serileştirme yardımcısı (örnek — render/outlook.py)
class WindowSegmentDict(TypedDict):
    start: str
    end: str
    level: Literal["ok", "watch", "danger"]
    gust_kn: float
    wave_m: float

class AreaOutlookDict(TypedDict):
    name: str
    lat: float | None
    lon: float | None
    windows: list[WindowSegmentDict]
    max_gust: float
    max_wave: float
    first_danger_start: str | None
    return_by: str | None
    worst: Literal["ok", "watch", "danger"]
```

`return_by` kuralı (domain):

1. `first_danger` varsa → o pencerenin `start` (veya bir slot önce — uygulama: **danger.start**).  
2. Else ilk `watch` varsa → `watch.start`.  
3. Else `null` (gün sakin).

### 2.3 Persistence DTO — `outlook.json` (Response / Public API)

Cycle’ın yazdığı, web + bot’un okuduğu **tek Response DTO**:

```typescript
export interface BoatClassLimits {
  label: string;
  gust_kn: number;
  wave_m: number;
}

export interface BoatClassOutlook {
  label: string;
  limits: BoatClassLimits;
  areas: AreaOutlook[];
}

/** web/data/outlook.json — schema_version 1 */
export interface OutlookFile {
  schema_version: 1;
  generated: IsoDateTime;
  hours: number;                 // e.g. 18
  tz_offset_hours: number;       // e.g. 3
  question: "today";             // UX sabiti — Bugün
  classes: Record<BoatClassId, BoatClassOutlook>;
}
```

**Request DTO (HTTP):** Yok — statik GET.  
**Bot “request”:** komut argümanları (aşağıda).

### 2.4 Bot komut DTO’ları (Request)

```typescript
/** /balikci [bölge] — parse sonrası */
export interface FishermanQuery {
  chat_id: number | string;
  area: string | null;           // null → abone areas[0] veya "Marmara Denizi"
  boat: BoatClassId;             // abone boat | "small"
}

/** /kazalar — filtre */
export interface IncidentsQuery {
  statuses: Array<"confirmed" | "probable" | "signal" | "resolved">;
  // default implementation: ["confirmed", "probable"]
  limit: number;                 // default 5
}
```

### 2.5 Bot / UI Response DTO’ları (mantıksal)

Telegram HTML string üretir; ara model test ve web için:

```typescript
export interface FishermanReportDto {
  question_today: {
    area: string;
    boat: BoatClassId;
    boat_label: string;
    windows: WindowSegment[];
    return_by: LocalHHMM | null;
    worst: WindowLevel;
  };
  question_now: {
    score: number | null;
    status: SafetyStatus | null;
    wave_m: number | null;
    wind_kn: number | null;
    gust_kn: number | null;
    sea_temp_c: number | null;
    current_kn: number | null;
    data_quality: DataQuality;
    recommendation_tr: string | null;
  } | null;
  disclaimer: string;
}

export interface IncidentListItemDto {
  id: string;
  type: string;
  type_tr?: string;
  status: "signal" | "probable" | "confirmed" | "resolved" | "false-positive";
  area: string | null;
  lat: number | null;
  lon: number | null;
  vessel_name: string | null;
  summary: string | null;
}
```

### 2.6 `safety_index.json` (additive, non-breaking)

```typescript
export interface MarineSafetyRatingDto {
  area: string;
  score: number;                 // 0..100
  status: SafetyStatus;
  wave_m: number | null;
  wind_kn: number;
  gust_kn: number;
  recommendation_tr: string;
  recommendation_en: string;
  sea_temp_c: number | null;
  current_kn: number | null;
  last_update: IsoDateTime;
  /** NEW optional */
  data_quality?: DataQuality;
  baseline_boat_class?: BoatClassId; // default "small"
}

export interface SafetyIndexFile {
  schema_version?: 1;
  generated: IsoDateTime;
  question?: "now";
  ratings: MarineSafetyRatingDto[];
}
```

`data_quality` kuralı:

- `wave_m == null && sea_temp_c == null` → `"unknown"` (skor aşırı iyimser basılmaz / status en fazla caution tavanı — uygulama safety_index’te).  
- Biri null → `"partial"`.  
- İkisi de dolu → `"ok"`.

### 2.7 `incidents.json` okuma birliği

```typescript
export interface IncidentVessel {
  name: string | null;
  mmsi: number | null;
  type?: string | null;
  callsign?: string | null;
}

export interface IncidentDto {
  id: string;
  type: string;
  status: string;
  confidence: number;
  severity: string;
  lat: number | null;
  lon: number | null;
  area: string | null;
  vessel: IncidentVessel | null;
  summary?: string | null;
  // ... mevcut store alanları korunur
}

/** Writer (store) bugün */
export type IncidentsFileWriter = IncidentDto[];

/** Reader (/kazalar) — toleranslı */
export type IncidentsFileReader =
  | IncidentDto[]
  | { incidents: IncidentDto[]; generated?: IsoDateTime };
```

Normalize fonksiyon sözleşmesi:

```typescript
function normalizeIncidents(data: unknown): IncidentDto[];
```

### 2.8 Config domain (okuma)

```typescript
export interface OutlookConfig {
  enabled: boolean;
  send_hour_local: number;
  tz_offset_hours: number;
  hours: number;
  boat_class: BoatClassId;
  web_default_class?: BoatClassId;
  classes: Record<BoatClassId, { label: string; gust_kn: number; wave_m: number }>;
}
```

### 2.9 CPA hygiene (yan domain — girdi tipi)

```typescript
export interface AisPositionInput {
  mmsi: number;
  lat: number;
  lon: number;
  sog?: number | null;
  cog?: number | null;
  nav_status?: number | null;
  msg_type?: string;
}

/** detect_cpa_risks öncesi: Map<mmsi, AisPositionInput> — son konum kazanır */
```

Çıktı `CpaEvent` şeması değişmez; self-pair üretilmez.

---

## 3. State yapısı

### 3.1 Global backend state

Yok (stateless cycle). Kalıcı state yalnızca:

| Dosya | Initial / boş | Not |
|-------|---------------|-----|
| `web/data/outlook.json` | Yoksa bot/web “derlenmedi” | Her cycle overwrite |
| `data/bot_subscribers.json` | `{}` | `boat: "small"`, `areas: []` default |

### 3.2 Web UI local state (`app.js`)

Mevcut `LAST` nesnesine additive alanlar (global sayfa state):

```typescript
/** Initial state — sayfa yükü */
export interface AppDataState {
  safety: SafetyIndexFile | null;
  weather: unknown | null;       // weather_overlay — mevcut
  outlook: OutlookFile | null;   // NEW
  // ... mevcut incidents/warnings vs. aynı kalır
}

export const initialAppDataState: AppDataState = {
  safety: null,
  weather: null,
  outlook: null,
};

/** Outlook panel local UI state */
export interface OutlookPanelState {
  boat: BoatClassId;             // initial: outlook yoksa "small" | config web_default
  area: string;                  // initial: ilk rating/area veya "Marmara Denizi"
}

export const initialOutlookPanelState: OutlookPanelState = {
  boat: "small",
  area: "Marmara Denizi",
};
```

Akış:

1. `getJSON("data/outlook.json")` → `LAST.outlook`.  
2. Select change → `OutlookPanelState` güncelle → DOM re-render (framework yok).  
3. `LAST.safety` ile aynı `area` soft-join → “Şimdi” alt satırı.

Persist: `localStorage` **zorunlu değil** (scope dışı). İsteğe bağlı sonraki milestone: `mw.outlook.boat`.

### 3.3 Bot process state

| State | Yapı | Initial |
|-------|------|---------|
| Subscriber record | `{ boat?: BoatClassId, areas?: string[], last_outlook?: "YYYY-MM-DD", ... }` | `boat: "small"` |
| In-memory | Yok (her komutta diskten JSON) | — |

Note 4 RAM’de outlook cache tutmak **zorunlu değil**; dosya okuma yeterli. İleride mtime’lı process cache opsiyonel.

### 3.4 State diyagramı (özet)

```
[Actions cycle]
    write OutlookFile v1
    write SafetyIndexFile (additive)
         │
         ▼
[Pages / disk] ──GET──► [AppDataState.outlook]
                    └──► [AppDataState.safety]
         │
         └──read──► [Bot FishermanQuery] → FishermanReportDto → Telegram HTML
```

---

## Doğrulama kuralları (type-safe runtime checklist)

| Kural | Seviye |
|-------|--------|
| `classes` üç anahtarı da var (`small\|medium\|large`) | render fail → log, dosya yazma veya boş areas |
| `level ∈ ok\|watch\|danger` | domain enum |
| `return_by` null veya `HH:MM` | serileştirme |
| `schema_version === 1` | web: yoksa yine dene (forward), bot: yoksa kabul (ilk deploy) |
| `incidents` normalize sonrası `Array.isArray` | `/kazalar` |
| CPA adaylarında unique `mmsi` | process |

---

## Uygulama notu (kod üretimi için)

1. Önce `OutlookFile` yazan `src/render/outlook.py` (TypedDict veya düz dict + test).  
2. `AreaOutlook.return_by` hesapını tek fonksiyonda topla (`window.py` veya render).  
3. JS’de `#outlook-panel` yalnızca `OutlookFile` alanlarını kullansın; uydurma saat yok.  
4. Yeni npm/TS build **yok** — bu dosya sözleşmedir; isteğe bağlı `web/types.js` JSDoc typedef.

---

*Şema drift’i önlemek için: writer testleri `schema_version: 1` snapshot assert eder.*
