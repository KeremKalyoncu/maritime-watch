# Veri Modeli ve Tipler — Honest Data Integrity

| Alan | Değer |
|------|--------|
| **Özellik** | `honest-data-integrity` |
| **Kalıcılık** | DB yok — `web/data/*.json` |
| **İlgili** | Feature · Architecture Map |

---

## 1. Veritabanı / şema

İlişkisel migration **yok**. Sözleşme genişlemesi JSON alanları.

### `outlook.json` (v1 → v1 + coverage)

```ts
interface OutlookCoverage {
  expected: number;          // config openmeteo.points.length
  present: number;           // areas with usable series
  missing: string[];         // area names absent this cycle
}

interface OutlookFile {
  schema_version: 1;
  generated: string;         // ISO UTC
  hours: number;
  tz_offset_hours: number;
  question: "today";
  coverage: OutlookCoverage; // YENİ
  classes: Record<"small"|"medium"|"large", BoatClassBlock>;
}

type WindowLevel = "ok" | "watch" | "danger" | "unknown"; // unknown YENİ

interface WindowSeg {
  start: string; end: string;
  level: WindowLevel;
  gust_kn: number | null;
  wave_m: number | null;
}
```

### Forecast point (internal)

```ts
interface ForecastPoint {
  name: string; lat: number; lon: number;
  times: string[];
  gusts: (number | null)[];
  waves: (number | null)[];
  wind_dirs?: (number | null)[];  // degrees, optional
  sea_temp_c?: number | null;
  current_kn?: number | null;
}
```

---

## 2. Type / domain kuralları

| Kural | Anlam |
|-------|--------|
| `gust == null && wave == null` | `level = unknown` |
| Tek ölçüm var | Sadece o ölçümle eşik; diğeri uydurulmaz |
| `score` yok | UI/bot asla default 85 basmaz |
| `coverage.missing` | Publish edilir; tüketiciler kullanıcıya gösterebilir |

---

## 3. State (web)

`LAST.outlook`, `LAST.warnings`, `LAST.safety` — mevcut. Ek UI state yok; stale, `Date.parse(outlook.generated)` ile türetilir.
