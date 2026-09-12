/* Maritime Watch — Next-Gen Static Maritime Map & Aggregator.
   Reads data/*.json, refreshes every 60s, supports PWA offline caching.
   No build tools, pure Vanilla JS + Leaflet. */
"use strict";

const COLORS = {
  confirmed: "#e5484d", probable: "#f5a524", signal: "#8b9bab",
  resolved: "#30a46c", "false-positive": "#4b5563", warning: "#3b82f6",
  "collision-risk": "#ef4444", rescue: "#10b981",
};

const BEAUFORT_COLORS = [
  "#38bdf8", "#38bdf8", "#38bdf8", "#38bdf8", // 0-3 (Calm/Breeze - Blue)
  "#34d399", "#34d399",                       // 4-5 (Moderate/Fresh - Green)
  "#f59e0b", "#f97316",                       // 6-7 (Near gale - Yellow/Orange)
  "#ef4444", "#dc2626",                       // 8-9 (Gale/Strong gale - Red)
  "#9333ea", "#7e22ce", "#581c87"             // 10-12 (Storm/Hurricane - Purple)
];

const T = {
  tr: {
    type: {
      grounding: "karaya oturma", collision: "çatışma (çarpışma)",
      "collision-risk": "çatışma riski (yakın geçiş)", drift: "sürüklenme",
      distress: "tehlike çağrısı", capsize: "alabora", fire: "yangın",
      sinking: "batma", "man-overboard": "denize adam düştü",
      rescue: "kurtarma operasyonu", unknown: "belirsiz"
    },
    status: {
      signal: "zayıf sinyal (doğrulanmadı)", probable: "kuvvetli ihtimal",
      confirmed: "doğrulandı (resmi)", resolved: "kapandı", "false-positive": "yanlış alarm"
    },
    ui: {
      tag: "Türkiye karasuları — AIS anomalileri + resmi açıklamalar, tek yerde.",
      timeline: "Zaman çizelgesi", stats: "İstatistik", allregions: "Tüm bölgeler",
      "l-confirmed": "doğrulandı", "l-probable": "olası", "l-signal": "sinyal (doğrulanmadı)",
      "l-resolved": "kapandı", "l-warning": "hava uyarısı",
      updated: "Son güncelleme", events: "olay", warnings: "uyarı", src: "Kaynak",
      live: "canlı",
      k_open: "açık olay", k_confirmed: "doğrulanmış", k_warn: "hava uyarısı",
      k_src: "kaynak canlı", k_upd: "son güncelleme",
      empty_t: "Kayıt bulunamadı",
      empty_b: "Arama veya filtre kriterlerine uygun açık deniz olayı bulunmuyor.",
      empty_clear: "Filtreleri Temizle",
      ago: m => m < 1 ? "az önce" : m < 60 ? `${Math.round(m)} dk önce`
        : m < 1440 ? `${Math.round(m / 60)} sa önce` : `${Math.round(m / 1440)} gün önce`,
      firstseen: "İlk görülme", lastupd: "Güncelleme", unloc: "konum belirsiz",
      people: "kişi bildirildi", confirmedby: "bağımsız kaynak doğruluyor",
      track_pts: n => `📍 ${n} nokta rota geçmişi`,
      stale: h => `⚠ Veri ~${h} saat eski — otomatik güncelleme gecikmiş olabilir. Acil durum için 158 / 112.`,
      sys: h => h ? `sistem: ${h.sources_ok}/${h.sources_total} kaynak · ${h.cycle_seconds}s` : "",
      disclaimer: 'Bu bir kurtarma servisi değildir. Acil durumda <strong>158</strong> (Sahil Güvenlik) / <strong>112</strong>.',
      sources: "Kaynaklar: aisstream.io · Open-Meteo · KEGM · SHOD · Sahil Güvenlik · MGM · GDACS · haber RSS · OpenSeaMap",
      share_btn: "📋 Raporu Paylaş",
      share_copied: "✅ Kaza raporu ve koordinatlar panoya kopyalandı.",
      emergency_btn: "Acil Rehber",
      playback_btn: "Zaman Makinesi",
      offline_msg: "Çevrimdışı Mod — İnternet bağlantısı yok, son önbellek gösteriliyor.",
      chip_all: "Tümü", chip_confirmed: "🚨 Doğrulandı", chip_warning: "🌊 Hava Uyarısı",
      chip_cpa: "💥 Çatışma Riski", chip_rescue: "⚓ Kurtarma",
    },
  },
  en: {
    type: {
      grounding: "grounding", collision: "collision",
      "collision-risk": "collision risk (close quarter)", drift: "drift",
      distress: "distress call", capsize: "capsize", fire: "fire",
      sinking: "sinking", "man-overboard": "man overboard",
      rescue: "rescue completed", unknown: "unknown"
    },
    status: {
      signal: "weak signal (unverified)", probable: "probable",
      confirmed: "confirmed", resolved: "closed", "false-positive": "false alarm"
    },
    ui: {
      tag: "Turkish waters — AIS anomalies + official statements in one place.",
      timeline: "Timeline", stats: "Stats", allregions: "All areas",
      "l-confirmed": "confirmed", "l-probable": "probable", "l-signal": "signal (unverified)",
      "l-resolved": "closed", "l-warning": "weather warning",
      updated: "Updated", events: "incidents", warnings: "warnings", src: "Source",
      live: "live",
      k_open: "open incidents", k_confirmed: "confirmed", k_warn: "weather warnings",
      k_src: "sources live", k_upd: "last update",
      empty_t: "Nothing on record here",
      empty_b: "No incidents or warnings match your search or filter criteria.",
      empty_clear: "Clear Filters",
      ago: m => m < 1 ? "just now" : m < 60 ? `${Math.round(m)} min ago`
        : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`,
      firstseen: "First seen", lastupd: "Updated", unloc: "location unknown",
      people: "people reported", confirmedby: "independent sources confirm",
      track_pts: n => `📍 ${n} pts track history`,
      stale: h => `⚠ Data is ~${h}h old — update may be delayed. Emergency: 158 / 112.`,
      sys: h => h ? `system: ${h.sources_ok}/${h.sources_total} sources · ${h.cycle_seconds}s` : "",
      disclaimer: 'This is not a rescue service. In an emergency call <strong>158</strong> (Coast Guard) / <strong>112</strong>.',
      sources: "Sources: aisstream.io · Open-Meteo · KEGM · SHOD · Coast Guard · GDACS · news RSS · OpenSeaMap",
      share_btn: "📋 Share Report",
      share_copied: "✅ Incident report and coordinates copied to clipboard.",
      emergency_btn: "Emergency Guide",
      playback_btn: "Time Machine",
      offline_msg: "Offline Mode — No network connection, showing cached data.",
      chip_all: "All", chip_confirmed: "🚨 Confirmed", chip_warning: "🌊 Warnings",
      chip_cpa: "💥 Collision Risk", chip_rescue: "⚓ Rescue",
    },
  },
};

let LANG = (localStorage.getItem("mw-lang") === "en") ? "en" : "tr";
const trType = t => T[LANG].type[t] || t;
const trStatus = s => T[LANG].status[s] || s;
const U = () => T[LANG].ui;

let REGION = "";           // active region filter ("" = all)
let CHIP = "all";          // active chip filter
let SEARCH_QUERY = "";     // active search term
let LAST = {
  incidents: [], warnings: [], summary: null, health: null,
  weather: null, straits: null, safety: null
};

// Playback State
let PLAYBACK = {
  active: false,
  playing: false,
  speed: 1,
  currentPercent: 100,
  timer: null,
  minTs: 0,
  maxTs: 0,
};

const MAP_OK = typeof L !== "undefined";
let map = null, layer = null, weatherLayer = null;
let activeTrackPolyline = null;
const markerById = {};

if (MAP_OK) {
  map = L.map("map", { zoomControl: true }).setView([39.5, 30.5], 6);
  map.on("popupclose", () => {
    if (activeTrackPolyline) {
      activeTrackPolyline.remove();
      activeTrackPolyline = null;
    }
  });

  // 100% Free basemaps (Zero API Key required)
  const esriDark = L.layerGroup([
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16, attribution: "&copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
    }),
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16, opacity: 0.8,
    })
  ]).addTo(map);

  const esriOcean = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 13, attribution: "&copy; Esri, GEBCO, NOAA, National Geographic",
  });

  const osmStandard = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: "&copy; OpenStreetMap contributors",
  });

  const seamarks = L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", {
    maxZoom: 18, opacity: 0.85, attribution: "&copy; OpenSeaMap",
  }).addTo(map);

  fetch("data/regions.geojson").then(r => r.ok ? r.json() : null).then(gj => {
    if (!gj) return;
    L.geoJSON(gj, {
      style: { color: "#3b82f6", weight: 1, opacity: 0.35, fill: false, dashArray: "4 4" },
      onEachFeature: (f, lyr) => lyr.bindTooltip(f.properties && f.properties.name || "", { sticky: true }),
    }).addTo(map);
  }).catch(() => {});

  layer = L.layerGroup().addTo(map);
  weatherLayer = L.layerGroup().addTo(map);

  const baseMaps = {
    "🌙 Koyu Deniz Haritası": esriDark,
    "🌊 Okyanus & Derinlik": esriOcean,
    "🗺️ Standart Harita": osmStandard,
  };

  const overlays = {
    "Deniz Durumu (Hava)": weatherLayer,
    "Olaylar & Uyarılar": layer,
    "⚓ Fener & Şamandıralar": seamarks,
  };
  L.control.layers(baseMaps, overlays, { position: "topright" }).addTo(map);
} else {
  const el = document.getElementById("map");
  if (el) {
    el.style.cssText = "display:flex;align-items:center;justify-content:center;padding:24px;text-align:center;color:#93a4b3";
    el.textContent = "Harita kütüphanesi yüklenemedi. Zaman çizelgesi ve kontroller çalışıyor.";
  }
}

const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtTime = iso => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString(LANG === "en" ? "en-GB" : "tr-TR", { dateStyle: "short", timeStyle: "short" }); };
const radiusFor = sev => ({ critical: 11, major: 9, minor: 7, info: 6 }[sev] || 7);

function highlightText(text, q) {
  if (!q || !text) return esc(text);
  const escaped = esc(text);
  const regex = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return escaped.replace(regex, '<mark class="highlight">$1</mark>');
}

function orgsOf(x) {
  const out = [];
  (x.sources || []).forEach(s => { const o = s.org || s.kind; if (o && out.indexOf(o) === -1) out.push(o); });
  if (!out.length && x.org) out.push(x.org);
  return out;
}

function showToast(msg) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  container.appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transform = "translateY(10px)";
    t.style.transition = "all 0.3s ease-out";
    setTimeout(() => t.remove(), 300);
  }, 2600);
}

function copyToClipboard(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => showToast(U().share_copied)).catch(() => {});
  } else {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); showToast(U().share_copied); } catch (e) {}
    ta.remove();
  }
}

function shareIncident(id) {
  const inc = LAST.incidents.find(x => x.id === id);
  if (!inc) return;
  const coord = (inc.lat && inc.lon) ? `https://maps.google.com/?q=${inc.lat},${inc.lon}` : "";
  const wx = inc.weather_context ? `\nHava: ${inc.weather_context.summary_tr}` : "";
  const text = `🌊 Maritime Watch Raporu:\n${trType(inc.type)} (${trStatus(inc.status)})\nBölge: ${inc.area || "Belirsiz"}\nTarih: ${fmtTime(inc.last_update)}${wx}\nHarita: ${coord}`;
  copyToClipboard(text);
}

// Generate an inline SVG sparkline path
function createSparklineSvg(vals, color, width, height) {
  if (!vals || vals.length < 2) return "";
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const step = width / (vals.length - 1);
  const pts = vals.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * (height - 6) - 3;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `<svg class="sparkline" width="${width}" height="${height}">
    <path d="M ${pts.join(" L ")}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
  </svg>`;
}

function incidentPopup(i) {
  const u = U();
  const unv = i.status === "signal" ? `<div class="badge-unverified">⚠ ${esc(trStatus("signal"))}</div>` : "";
  const trackInfo = (i.track && i.track.length > 1) ? `<div class="popup-track">${u.track_pts(i.track.length)}</div>` : "";
  const srcs = (i.sources || []).map(s => {
    const link = s.url ? ` — <a href="${esc(s.url)}" target="_blank" rel="noopener">link</a>` : "";
    return `<li>${esc(s.org || s.kind)}: ${esc(s.detail)}${link}</li>`;
  }).join("");
  const vessel = (i.vessel && i.vessel.name) ? `⛴️ ${esc(i.vessel.name)}<br>` : "";
  const wxCtx = i.weather_context ? `<div class="popup-meta" style="color:#38bdf8;margin-top:3px">🌬️ ${esc(i.weather_context.summary_tr)}</div>` : "";

  return `<div class="popup-title">${esc(trType(i.type))} — ${esc(trStatus(i.status))}</div>${unv}${trackInfo}
    <div class="popup-meta">${esc(i.area || u.unloc)}${i.casualties ? " · " + i.casualties + " " + u.people : ""}<br>
    ${vessel}${u.src}: ${esc(orgsOf(i).join(", "))}<br>
    ${u.firstseen}: ${fmtTime(i.first_seen)} · ${u.lastupd}: ${fmtTime(i.last_update)}</div>
    ${wxCtx}
    <ul style="margin:6px 0 0 16px;padding:0">${srcs}</ul>
    <button type="button" class="btn-share" onclick="shareIncident('${esc(i.id)}')">📋 ${esc(u.share_btn)}</button>`;
}

function warningPopup(w) {
  const o = orgsOf(w);
  const multi = o.length >= 2 ? `<div class="badge-unverified">✅ ${o.length} ${U().confirmedby}</div>` : "";
  return `<div class="popup-title">🌊 ${esc(w.headline)}</div>${multi}
    <div class="popup-meta">${esc(w.area)} · ${esc(o.join(", "))}<br>${fmtTime(w.issued)}</div>
    ${w.url ? `<a href="${esc(w.url)}" target="_blank" rel="noopener">link</a>` : ""}`;
}

function weatherPointPopup(p) {
  const bColor = BEAUFORT_COLORS[Math.min(p.beaufort, BEAUFORT_COLORS.length - 1)];
  const wavesSpark = p.trend_12h && p.trend_12h.waves ? createSparklineSvg(p.trend_12h.waves, "#38bdf8", 180, 26) : "";
  const windsSpark = p.trend_12h && p.trend_12h.winds ? createSparklineSvg(p.trend_12h.winds, bColor, 180, 26) : "";

  return `<div class="popup-title">🌊 ${esc(p.name)}</div>
    <div class="popup-meta">
      <span class="safety-badge ${p.rating}">${p.rating.toUpperCase()}</span> · Bft ${p.beaufort}
      <br>Rüzgar: <strong>${p.wind_kn} kn</strong> (Hamle: ${p.gust_kn} kn) · Yön: ${p.wind_dir}°
      <br>Dalga: <strong>${p.wave_m != null ? p.wave_m + " m" : "—"}</strong>
    </div>
    ${wavesSpark ? `<div class="sparkline-box"><div class="sparkline-label">12 Saatlik Dalga Trendi (m)</div>${wavesSpark}</div>` : ""}
    ${windsSpark ? `<div class="sparkline-box"><div class="sparkline-label">12 Saatlik Rüzgar Hamlesi (kn)</div>${windsSpark}</div>` : ""}`;
}

const ICON = {
  grounding: "⛰️", collision: "💥", "collision-risk": "⚠️", drift: "🧭", distress: "🆘",
  capsize: "🔃", fire: "🔥", sinking: "⬇️", "man-overboard": "🏊", rescue: "✅",
  unknown: "❓", warning: "🌊",
};

function agoText(iso) {
  const t = Date.parse(iso);
  if (!t || isNaN(t)) return "";
  return U().ago(Math.max(0, (Date.now() - t) / 60000));
}

function renderSafetyStrip(straitsData, safetyData) {
  const strip = document.getElementById("safety-strip");
  if (!strip) return;

  const cards = [];

  // 1. Straits
  (straitsData ? straitsData.straits || [] : []).forEach(st => {
    const isSusp = st.status === "suspended";
    const badgeClass = isSusp ? "suspended" : (st.status === "caution" ? "caution" : "good");
    const meta = isSusp ? `⚠ ${st.reason || ""}` : `${st.active_vessels_in_transit} transit gemi · ${st.avg_speed_kn} kn`;
    cards.push(`
      <div class="safety-card" onclick="focusStrait('${st.id}')">
        <span class="sc-title">${esc(st.name)}:</span>
        <span class="safety-badge ${badgeClass}">${esc(st.status_tr)}</span>
        <span class="sc-meta">${esc(meta)}</span>
      </div>
    `);
  });

  // 2. Coastal Safety Lowest Rating
  if (safetyData && safetyData.ratings && safetyData.ratings.length) {
    const danger = safetyData.ratings.filter(r => r.status === "danger");
    const caution = safetyData.ratings.filter(r => r.status === "caution");
    if (danger.length > 0) {
      cards.push(`
        <div class="safety-card" onclick="filterChip('warning')">
          <span class="sc-title">⚠️ Balıkçı Güvenlik Uyarısı:</span>
          <span class="safety-badge danger">${danger.length} Bölgede Fırtına</span>
          <span class="sc-meta">${esc(danger.map(d => d.area).slice(0, 2).join(", "))}</span>
        </div>
      `);
    } else if (caution.length > 0) {
      cards.push(`
        <div class="safety-card">
          <span class="sc-title">Sefer Skoru:</span>
          <span class="safety-badge caution">Tedbirli Seyir (${caution.length} bölge)</span>
        </div>
      `);
    } else {
      cards.push(`
        <div class="safety-card">
          <span class="sc-title">Sefer Skoru:</span>
          <span class="safety-badge good">🟢 Karasularımız Elverişli</span>
        </div>
      `);
    }
  }

  strip.innerHTML = cards.join("");
}

function focusStrait(id) {
  if (!map) return;
  if (id === "bosphorus") {
    map.flyTo([41.12, 29.08], 11, { duration: 0.8 });
  } else if (id === "dardanelles") {
    map.flyTo([40.20, 26.40], 11, { duration: 0.8 });
  }
}

function renderKpis(incidents, warnings, summary, health) {
  const u = U();
  const open = incidents.filter(i => i.status !== "resolved" && i.status !== "false-positive");
  const confirmed = open.filter(i => i.status === "confirmed");
  const ok = health ? health.sources_ok : null;
  const total = health ? health.sources_total : null;
  const degraded = ok !== null && total ? ok < total : false;
  const cells = [
    { v: open.length, l: u.k_open, c: "" },
    { v: confirmed.length, l: u.k_confirmed, c: confirmed.length ? "is-confirmed" : "" },
    { v: warnings.length, l: u.k_warn, c: warnings.length ? "is-warning" : "" },
    { v: ok === null ? "—" : ok + "/" + total, l: u.k_src, c: degraded ? "is-degraded" : "is-ok" },
    { v: summary ? (agoText(summary.generated) || "—") : "—", l: u.k_upd, c: "" },
  ];
  document.getElementById("kpis").innerHTML = cells.map(c =>
    `<div class="kpi ${c.c}"><div class="k-val">${esc(String(c.v))}</div><div class="k-lab">${esc(c.l)}</div></div>`
  ).join("");
}

function matchesItem(it) {
  // 1. Region filter
  if (REGION && it.area !== REGION) return false;

  // 2. Chip filter
  if (CHIP === "confirmed" && it.status !== "confirmed") return false;
  if (CHIP === "warning" && it._kind !== "warning") return false;
  if (CHIP === "collision-risk" && it.type !== "collision-risk") return false;
  if (CHIP === "rescue" && it.type !== "rescue") return false;

  // 3. Playback time filter
  if (PLAYBACK.active) {
    const stamp = it._kind === "warning" ? it.issued : it.last_update;
    const ts = Date.parse(stamp) || 0;
    const threshold = PLAYBACK.minTs + (PLAYBACK.maxTs - PLAYBACK.minTs) * (PLAYBACK.currentPercent / 100);
    if (ts > threshold) return false;
  }

  // 4. Search query
  if (SEARCH_QUERY) {
    const q = SEARCH_QUERY.toLowerCase();
    const hay = [
      it.area, it.type, it.headline, trType(it.type),
      (it.vessel && it.vessel.name),
      ...(it.sources || []).map(s => s.detail),
      ...(it.notes || [])
    ].filter(Boolean).join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }

  return true;
}

function addTimeline(items) {
  const ol = document.getElementById("timeline");
  ol.innerHTML = "";
  items.forEach(it => {
    const li = document.createElement("li");
    li.className = it._kind === "warning" ? "warning" : it.status;
    const stamp = it._kind === "warning" ? it.issued : it.last_update;
    const when = agoText(stamp) || fmtTime(stamp);
    const title = it._kind === "warning" ? (it.headline || "").slice(0, 65) : trType(it.type);
    const ico = it._kind === "warning" ? ICON.warning : (ICON[it.type] || ICON.unknown);
    const badge = it._kind === "warning" ? "" : trStatus(it.status);
    const src = (it.sources || [])[0];
    const srcText = it._kind === "warning" ? orgsOf(it).join(", ") : (src ? src.org || src.kind : "");

    li.innerHTML = `
      <div class="t-head">
        <span class="t-type">
          <span class="t-ico">${ico}</span>
          <span class="t-txt">${highlightText(title, SEARCH_QUERY)}</span>
        </span>
        <span class="t-badge">${esc(badge)}</span>
      </div>
      <div class="t-area">${highlightText(it.area || U().unloc, SEARCH_QUERY)} · <span class="t-when">${esc(when)}</span></div>
      <div class="t-src">${highlightText(srcText, SEARCH_QUERY)}</div>
    `;
    li.onclick = () => {
      const m = markerById[it._id];
      if (m && map) {
        map.setView(m.getLatLng(), 10);
        m.openPopup();
      }
    };
    ol.appendChild(li);
  });

  const empty = document.getElementById("empty");
  if (empty) {
    empty.innerHTML = `
      <b>${esc(U().empty_t)}</b>
      ${esc(U().empty_b)}
      <br><button type="button" class="btn" style="margin-top:8px" onclick="clearFilters()">${esc(U().empty_clear)}</button>
    `;
    empty.hidden = items.length > 0;
  }
}

function clearFilters() {
  SEARCH_QUERY = "";
  CHIP = "all";
  REGION = "";
  const input = document.getElementById("search-input");
  if (input) input.value = "";
  const sel = document.getElementById("region");
  if (sel) sel.value = "";
  document.querySelectorAll(".chip").forEach(c => c.classList.toggle("is-active", c.dataset.chip === "all"));
  render();
}

function drawWeatherOverlay(points) {
  if (!MAP_OK || !weatherLayer) return;
  weatherLayer.clearLayers();
  if (!points || !points.length) return;

  points.forEach(p => {
    if (p.lat == null || p.lon == null) return;
    const bColor = BEAUFORT_COLORS[Math.min(p.beaufort, BEAUFORT_COLORS.length - 1)];

    const iconHtml = `
      <div class="weather-marker">
        <svg class="weather-arrow" viewBox="0 0 24 24" style="transform: rotate(${p.wind_dir}deg)">
          <path d="M12 2 L19 21 L12 17 L5 21 Z" fill="${bColor}" stroke="#0a101d" stroke-width="1.5" />
        </svg>
        <span class="weather-pill">${p.wave_m != null ? p.wave_m + "m" : p.wind_kn + "kn"}</span>
      </div>
    `;

    const icon = L.divIcon({
      html: iconHtml,
      className: "weather-div-icon",
      iconSize: [32, 36],
      iconAnchor: [16, 18],
    });

    const m = L.marker([p.lat, p.lon], { icon }).bindPopup(weatherPointPopup(p));
    m.addTo(weatherLayer);
  });
}

function drawMarkers(incidents, warnings) {
  if (!MAP_OK) return;
  if (activeTrackPolyline) {
    activeTrackPolyline.remove();
    activeTrackPolyline = null;
  }
  layer.clearLayers();
  for (const k in markerById) delete markerById[k];

  incidents.filter(matchesItem).forEach(i => {
    if (i.lat == null || i.lon == null) return;
    const c = COLORS[i.status] || COLORS.signal;
    const m = L.circleMarker([i.lat, i.lon], {
      radius: radiusFor(i.severity),
      color: c,
      weight: i.status === "signal" ? 1 : 2,
      dashArray: i.status === "signal" ? "3 3" : null,
      fillColor: c,
      fillOpacity: i.status === "signal" ? 0.25 : 0.65,
    }).bindPopup(incidentPopup(i));

    if (i.track && i.track.length > 1) {
      m.on("popupopen", () => {
        if (activeTrackPolyline) activeTrackPolyline.remove();
        activeTrackPolyline = L.polyline(i.track, {
          color: COLORS[i.status] || "#f5a524",
          weight: 3,
          opacity: 0.85,
          dashArray: "6, 6",
        }).addTo(map);
      });
      m.on("popupclose", () => {
        if (activeTrackPolyline) {
          activeTrackPolyline.remove();
          activeTrackPolyline = null;
        }
      });
    }

    m.addTo(layer);
    markerById[i.id] = m;
  });

  warnings.filter(matchesItem).forEach(w => {
    if (w.lat == null || w.lon == null) return;
    const m = L.circleMarker([w.lat, w.lon], {
      radius: 10,
      color: COLORS.warning,
      weight: 2,
      fillColor: COLORS.warning,
      fillOpacity: 0.18,
    }).bindPopup(warningPopup(w));
    m.addTo(layer);
    markerById["w:" + w.id] = m;
  });
}

async function getJSON(path) {
  try {
    const r = await fetch(path + "?" + Date.now(), { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch (e) {
    return null;
  }
}

function applyI18n() {
  document.documentElement.lang = LANG;
  document.getElementById("lang").textContent = LANG === "en" ? "TR" : "EN";
  document.querySelectorAll("[data-i]").forEach(el => {
    const v = U()[el.dataset.i];
    if (typeof v === "string") el.innerHTML = v;
  });
}

function fillRegions(incidents, warnings) {
  const sel = document.getElementById("region");
  const areas = [...new Set([...incidents, ...warnings].map(x => x.area).filter(Boolean))].sort();
  const cur = sel.value;
  sel.innerHTML = `<option value="">${U().allregions}</option>` +
    areas.map(a => `<option value="${esc(a)}">${esc(a)}</option>`).join("");
  sel.value = areas.includes(cur) ? cur : "";
  REGION = sel.value;
}

function render() {
  const { incidents, warnings, summary, health, straits, safety, weather } = LAST;
  drawMarkers(incidents, warnings);
  if (weather && weather.points) {
    drawWeatherOverlay(weather.points);
  }

  const tl = []
    .concat(incidents.filter(matchesItem).map(i => ({ ...i, _kind: "incident", _id: i.id })))
    .concat(warnings.filter(matchesItem).map(w => ({ ...w, _kind: "warning", _id: "w:" + w.id })))
    .sort((a, b) => String(b.last_update || b.issued || "").localeCompare(String(a.last_update || a.issued || "")))
    .slice(0, 40);

  addTimeline(tl);
  renderSafetyStrip(straits, safety);

  const u = U();
  renderKpis(incidents.filter(matchesItem), warnings.filter(matchesItem), summary, health);
  document.getElementById("sys").textContent = u.sys(health);

  const stale = document.getElementById("stale");
  const genMs = summary && Date.parse(summary.generated);
  const limitH = (summary && summary.stale_hours) || 2;
  if (genMs && !isNaN(genMs) && (Date.now() - genMs) / 3600000 > limitH) {
    stale.textContent = u.stale(Math.round((Date.now() - genMs) / 3600000));
    stale.hidden = false;
  } else {
    stale.hidden = true;
  }
}

async function load() {
  LAST.incidents = (await getJSON("data/incidents.json")) || [];
  LAST.warnings = (await getJSON("data/warnings.json")) || [];
  LAST.summary = await getJSON("data/summary.json");
  LAST.health = await getJSON("data/health.json");
  LAST.straits = await getJSON("data/straits.json");
  LAST.safety = await getJSON("data/safety_index.json");
  LAST.weather = await getJSON("data/weather_overlay.json");

  // Compute time bounds for playback
  const allStamps = [...LAST.incidents.map(i => i.first_seen || i.last_update), ...LAST.warnings.map(w => w.issued)]
    .map(s => Date.parse(s))
    .filter(t => !isNaN(t) && t > 0);
  if (allStamps.length > 0) {
    PLAYBACK.minTs = Math.min(...allStamps);
    PLAYBACK.maxTs = Math.max(...allStamps, Date.now());
  } else {
    PLAYBACK.minTs = Date.now() - 48 * 3600 * 1000;
    PLAYBACK.maxTs = Date.now();
  }

  fillRegions(LAST.incidents, LAST.warnings);
  render();
}

function focusHash() {
  const id = decodeURIComponent((location.hash || "").slice(1));
  if (!id || !map) return;
  const m = markerById[id] || markerById["w:" + id];
  if (m) {
    map.setView(m.getLatLng(), 10);
    m.openPopup();
  }
}

// ---------------- UI Event Handlers ----------------

// Lang toggle
document.getElementById("lang").addEventListener("click", () => {
  LANG = LANG === "en" ? "tr" : "en";
  try { localStorage.setItem("mw-lang", LANG); } catch (e) {}
  applyI18n();
  render();
});

// Region selector
document.getElementById("region").addEventListener("change", e => {
  REGION = e.target.value;
  render();
});

// Search input with 150ms debounce
let searchDebounceTimer = null;
const searchInput = document.getElementById("search-input");
if (searchInput) {
  searchInput.addEventListener("input", e => {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      SEARCH_QUERY = e.target.value.trim();
      render();
      if (SEARCH_QUERY && document.getElementById("empty") && !document.getElementById("empty").hidden) {
        const box = document.querySelector(".search-box");
        if (box) {
          box.classList.add("shake");
          setTimeout(() => box.classList.remove("shake"), 350);
        }
      }
    }, 150);
  });
  searchInput.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      clearFilters();
    }
  });
}

// Filter chips
function filterChip(chip) {
  CHIP = chip;
  document.querySelectorAll(".chip").forEach(c => c.classList.toggle("is-active", c.dataset.chip === chip));
  render();
}
document.querySelectorAll(".chip").forEach(c => {
  c.addEventListener("click", () => filterChip(c.dataset.chip));
});

// Emergency Modal
const emergencyModal = document.getElementById("emergency-modal");
const btnEmergency = document.getElementById("btn-emergency");
const modalClose = document.getElementById("modal-close");
const modalBackdrop = document.getElementById("modal-backdrop");

if (btnEmergency && emergencyModal) {
  btnEmergency.addEventListener("click", () => { emergencyModal.hidden = false; });
  if (modalClose) modalClose.addEventListener("click", () => { emergencyModal.hidden = true; });
  if (modalBackdrop) modalBackdrop.addEventListener("click", () => { emergencyModal.hidden = true; });
  window.addEventListener("keydown", e => { if (e.key === "Escape") emergencyModal.hidden = true; });
}

// Copy buttons inside emergency modal
document.querySelectorAll(".btn-copy").forEach(btn => {
  btn.addEventListener("click", () => {
    copyToClipboard(btn.dataset.copy);
  });
});

// Playback Bar Logic
const playbackBar = document.getElementById("playback-bar");
const btnTogglePlayback = document.getElementById("btn-toggle-playback");
const playBtn = document.getElementById("play-btn");
const playRange = document.getElementById("play-range");
const playTime = document.getElementById("play-time");
const playClose = document.getElementById("play-close");

if (btnTogglePlayback && playbackBar) {
  btnTogglePlayback.addEventListener("click", () => {
    PLAYBACK.active = !PLAYBACK.active;
    playbackBar.hidden = !PLAYBACK.active;
    if (!PLAYBACK.active) {
      PLAYBACK.playing = false;
      PLAYBACK.currentPercent = 100;
      clearInterval(PLAYBACK.timer);
      playBtn.textContent = "▶";
    }
    render();
  });

  if (playClose) {
    playClose.addEventListener("click", () => {
      PLAYBACK.active = false;
      PLAYBACK.playing = false;
      playbackBar.hidden = true;
      clearInterval(PLAYBACK.timer);
      playBtn.textContent = "▶";
      render();
    });
  }

  function updatePlayTimeLabel() {
    if (PLAYBACK.currentPercent >= 100) {
      playTime.textContent = "Canlı";
    } else {
      const curTs = PLAYBACK.minTs + (PLAYBACK.maxTs - PLAYBACK.minTs) * (PLAYBACK.currentPercent / 100);
      playTime.textContent = fmtTime(new Date(curTs).toISOString());
    }
  }

  playRange.addEventListener("input", e => {
    PLAYBACK.currentPercent = parseFloat(e.target.value);
    updatePlayTimeLabel();
    render();
  });

  playBtn.addEventListener("click", () => {
    PLAYBACK.playing = !PLAYBACK.playing;
    playBtn.textContent = PLAYBACK.playing ? "⏸" : "▶";
    if (PLAYBACK.playing) {
      if (PLAYBACK.currentPercent >= 100) PLAYBACK.currentPercent = 0;
      clearInterval(PLAYBACK.timer);
      PLAYBACK.timer = setInterval(() => {
        PLAYBACK.currentPercent += 1 * PLAYBACK.speed;
        if (PLAYBACK.currentPercent >= 100) {
          PLAYBACK.currentPercent = 100;
          PLAYBACK.playing = false;
          playBtn.textContent = "▶";
          clearInterval(PLAYBACK.timer);
        }
        playRange.value = PLAYBACK.currentPercent;
        updatePlayTimeLabel();
        render();
      }, 100);
    } else {
      clearInterval(PLAYBACK.timer);
    }
  });

  document.querySelectorAll(".speed-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".speed-btn").forEach(b => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      PLAYBACK.speed = parseFloat(btn.dataset.speed) || 1;
    });
  });
}

// Service Worker & Offline detection
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(err => console.warn("[pwa] sw err:", err));
}
function updateOfflineStatus(isOffline) {
  const bar = document.getElementById("offline-bar");
  if (bar) bar.hidden = !isOffline;
}
window.addEventListener("online", () => updateOfflineStatus(false));
window.addEventListener("offline", () => updateOfflineStatus(true));
if (!navigator.onLine) updateOfflineStatus(true);

window.addEventListener("hashchange", focusHash);
window.shareIncident = shareIncident;
window.focusStrait = focusStrait;
window.filterChip = filterChip;
window.clearFilters = clearFilters;

applyI18n();
load().then(focusHash);
setInterval(load, 60000);
