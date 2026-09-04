/* Maritime Watch — static map. Reads data/*.json, refreshes every 60s.
   Degrades gracefully: if the Leaflet CDN is unreachable the timeline and the
   counters still render, with a note where the map would be. */
"use strict";

const COLORS = {
  confirmed: "#e5484d", probable: "#f5a524", signal: "#8b9bab",
  resolved: "#30a46c", "false-positive": "#4b5563", warning: "#3b82f6",
};

const T = {
  tr: {
    type: { grounding: "karaya oturma", collision: "çatışma", drift: "sürüklenme",
      distress: "tehlike çağrısı", capsize: "alabora", fire: "yangın", sinking: "batma",
      "man-overboard": "denize adam düştü", unknown: "belirsiz" },
    status: { signal: "zayıf sinyal (doğrulanmadı)", probable: "kuvvetli ihtimal",
      confirmed: "doğrulandı", resolved: "kapandı", "false-positive": "yanlış alarm" },
    ui: {
      tag: "Türkiye karasuları — AIS anomalileri + resmi açıklamalar, tek yerde. Sinyaller doğrulanana kadar “doğrulanmadı” etiketlidir.",
      timeline: "Zaman çizelgesi", stats: "İstatistik", allregions: "Tüm bölgeler",
      "l-confirmed": "doğrulandı", "l-probable": "olası", "l-signal": "sinyal (doğrulanmadı)",
      "l-resolved": "kapandı", "l-warning": "hava uyarısı",
      updated: "Son güncelleme", events: "olay", warnings: "uyarı", src: "Kaynak",
      firstseen: "İlk görülme", lastupd: "Güncelleme", unloc: "konum belirsiz",
      people: "kişi bildirildi", confirmedby: "bağımsız kaynak doğruluyor",
      stale: h => `⚠ Veri ~${h} saat eski — otomatik güncelleme gecikmiş olabilir. Acil durum için 158 / 112.`,
      sys: h => h ? `sistem: ${h.sources_ok}/${h.sources_total} kaynak · ${h.cycle_seconds}s` : "",
      disclaimer: 'Bu bir kurtarma servisi değildir. Acil durumda <strong>158</strong> (Sahil Güvenlik) / <strong>112</strong>.',
      sources: "Kaynaklar: aisstream.io · Open-Meteo · AFAD/USGS/EMSC · Sahil Güvenlik · GDACS · NASA EONET · haber RSS · OpenSeaMap",
    },
  },
  en: {
    type: { grounding: "grounding", collision: "collision", drift: "drift",
      distress: "distress call", capsize: "capsize", fire: "fire", sinking: "sinking",
      "man-overboard": "man overboard", unknown: "unknown" },
    status: { signal: "weak signal (unverified)", probable: "probable",
      confirmed: "confirmed", resolved: "closed", "false-positive": "false alarm" },
    ui: {
      tag: "Turkish waters — AIS anomalies + official statements in one place. Signals are labelled “unverified” until confirmed.",
      timeline: "Timeline", stats: "Stats", allregions: "All areas",
      "l-confirmed": "confirmed", "l-probable": "probable", "l-signal": "signal (unverified)",
      "l-resolved": "closed", "l-warning": "weather warning",
      updated: "Updated", events: "incidents", warnings: "warnings", src: "Source",
      firstseen: "First seen", lastupd: "Updated", unloc: "location unknown",
      people: "people reported", confirmedby: "independent sources confirm",
      stale: h => `⚠ Data is ~${h}h old — the scheduled update may be delayed. Emergency: 158 / 112.`,
      sys: h => h ? `system: ${h.sources_ok}/${h.sources_total} sources · ${h.cycle_seconds}s` : "",
      disclaimer: 'This is not a rescue service. In an emergency call <strong>158</strong> (Coast Guard) / <strong>112</strong>.',
      sources: "Sources: aisstream.io · Open-Meteo · AFAD/USGS/EMSC · Coast Guard · GDACS · NASA EONET · news RSS · OpenSeaMap",
    },
  },
};

let LANG = (localStorage.getItem("mw-lang") === "en") ? "en" : "tr";
const trType = t => T[LANG].type[t] || t;
const trStatus = s => T[LANG].status[s] || s;
const U = () => T[LANG].ui;

let REGION = "";           // active region filter ("" = all)
let LAST = { incidents: [], warnings: [], summary: null, health: null };

const MAP_OK = typeof L !== "undefined";
let map = null, layer = null;
const markerById = {};

if (MAP_OK) {
  map = L.map("map", { zoomControl: true }).setView([39.5, 30.5], 6);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "&copy; OpenStreetMap" }).addTo(map);
  L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", { maxZoom: 18, opacity: 0.9, attribution: "&copy; OpenSeaMap" }).addTo(map);
  fetch("data/regions.geojson").then(r => r.ok ? r.json() : null).then(gj => {
    if (!gj) return;
    L.geoJSON(gj, {
      style: { color: "#3b82f6", weight: 1, opacity: 0.35, fill: false, dashArray: "4 4" },
      onEachFeature: (f, lyr) => lyr.bindTooltip(f.properties && f.properties.name || "", { sticky: true }),
    }).addTo(map);
  }).catch(() => {});
  layer = L.layerGroup().addTo(map);
} else {
  const el = document.getElementById("map");
  if (el) {
    el.style.cssText = "display:flex;align-items:center;justify-content:center;padding:24px;text-align:center;color:#93a4b3";
    el.textContent = "Harita kütüphanesi (Leaflet CDN) yüklenemedi. Zaman çizelgesi ve sayaçlar çalışıyor.";
  }
}

const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtTime = iso => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString(LANG === "en" ? "en-GB" : "tr-TR", { dateStyle: "short", timeStyle: "short" }); };
const radiusFor = sev => ({ critical: 11, major: 9, minor: 7, info: 6 }[sev] || 7);
const inRegion = it => !REGION || it.area === REGION;

function orgsOf(x) {
  const out = [];
  (x.sources || []).forEach(s => { const o = s.org || s.kind; if (o && out.indexOf(o) === -1) out.push(o); });
  if (!out.length && x.org) out.push(x.org);
  return out;
}

function incidentPopup(i) {
  const u = U();
  const unv = i.status === "signal" ? `<div class="badge-unverified">⚠ ${esc(trStatus("signal"))}</div>` : "";
  const srcs = (i.sources || []).map(s => {
    const link = s.url ? ` — <a href="${esc(s.url)}" target="_blank" rel="noopener">link</a>` : "";
    return `<li>${esc(s.org || s.kind)}: ${esc(s.detail)}${link}</li>`;
  }).join("");
  const vessel = (i.vessel && i.vessel.name) ? `⛴️ ${esc(i.vessel.name)}<br>` : "";
  return `<div class="popup-title">${esc(trType(i.type))} — ${esc(trStatus(i.status))}</div>${unv}
    <div class="popup-meta">${esc(i.area || u.unloc)}${i.casualties ? " · " + i.casualties + " " + u.people : ""}<br>
    ${vessel}${u.src}: ${esc(orgsOf(i).join(", "))}<br>
    ${u.firstseen}: ${fmtTime(i.first_seen)} · ${u.lastupd}: ${fmtTime(i.last_update)}</div>
    <ul style="margin:6px 0 0 16px;padding:0">${srcs}</ul>`;
}

function warningPopup(w) {
  const o = orgsOf(w);
  const multi = o.length >= 2 ? `<div class="badge-unverified">✅ ${o.length} ${U().confirmedby}</div>` : "";
  return `<div class="popup-title">🌊 ${esc(w.headline)}</div>${multi}
    <div class="popup-meta">${esc(w.area)} · ${esc(o.join(", "))}<br>${fmtTime(w.issued)}</div>
    ${w.url ? `<a href="${esc(w.url)}" target="_blank" rel="noopener">link</a>` : ""}`;
}

function addTimeline(items) {
  const ol = document.getElementById("timeline");
  ol.innerHTML = "";
  items.forEach(it => {
    const li = document.createElement("li");
    li.className = it._kind === "warning" ? "warning" : it.status;
    const when = fmtTime(it._kind === "warning" ? it.issued : it.last_update);
    const title = it._kind === "warning" ? "⚠" : trType(it.type);
    const badge = it._kind === "warning" ? "" : trStatus(it.status);
    const src = (it.sources || [])[0];
    const srcHtml = it._kind === "warning" ? esc(orgsOf(it).join(", "))
      : (src ? `${esc(src.org || src.kind)}${src.url ? ` — <a href="${esc(src.url)}" target="_blank" rel="noopener">link</a>` : ""}` : "");
    li.innerHTML = `<div class="t-head"><span class="t-type">${esc(title)}</span><span class="t-badge">${esc(badge)}</span></div>
      <div class="t-area">${esc(it.area || U().unloc)} · ${when}</div><div class="t-src">${srcHtml}</div>`;
    li.onclick = () => { const m = markerById[it._id]; if (m && map) { map.setView(m.getLatLng(), 9); m.openPopup(); } };
    ol.appendChild(li);
  });
}

function drawMarkers(incidents, warnings) {
  if (!MAP_OK) return;
  if (layer) layer.remove();
  layer = L.layerGroup().addTo(map);
  for (const k in markerById) delete markerById[k];
  incidents.filter(inRegion).forEach(i => {
    if (i.lat == null || i.lon == null) return;
    const c = COLORS[i.status] || COLORS.signal;
    const m = L.circleMarker([i.lat, i.lon], {
      radius: radiusFor(i.severity), color: c, weight: i.status === "signal" ? 1 : 2,
      dashArray: i.status === "signal" ? "3 3" : null, fillColor: c,
      fillOpacity: i.status === "signal" ? 0.25 : 0.6,
    }).bindPopup(incidentPopup(i));
    m.addTo(layer); markerById[i.id] = m;
  });
  warnings.filter(inRegion).forEach(w => {
    if (w.lat == null || w.lon == null) return;
    const m = L.circleMarker([w.lat, w.lon], {
      radius: 10, color: COLORS.warning, weight: 2, fillColor: COLORS.warning, fillOpacity: 0.15,
    }).bindPopup(warningPopup(w));
    m.addTo(layer); markerById["w:" + w.id] = m;
  });
}

async function getJSON(path) {
  try {
    const r = await fetch(path + "?" + Date.now(), { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch (e) { return null; }
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
  const { incidents, warnings, summary, health } = LAST;
  drawMarkers(incidents, warnings);
  const tl = []
    .concat(incidents.filter(inRegion).map(i => ({ ...i, _kind: "incident", _id: i.id })))
    .concat(warnings.filter(inRegion).map(w => ({ ...w, _kind: "warning", _id: "w:" + w.id })))
    .sort((a, b) => String(b.last_update || b.issued || "").localeCompare(String(a.last_update || a.issued || "")))
    .slice(0, 40);
  addTimeline(tl);

  const u = U();
  const gen = summary ? fmtTime(summary.generated) : "—";
  const bs = summary && summary.by_status
    ? Object.entries(summary.by_status).map(([k, v]) => `${trStatus(k)}: ${v}`).join(" · ") : "";
  document.getElementById("meta").textContent =
    `${u.updated}: ${gen}  ·  ${incidents.length} ${u.events}${bs ? " (" + bs + ")" : ""}  ·  ${warnings.length} ${u.warnings}`;
  document.getElementById("sys").textContent = u.sys(health);

  const stale = document.getElementById("stale");
  const genMs = summary && Date.parse(summary.generated);
  const limitH = (summary && summary.stale_hours) || 2;
  if (genMs && !isNaN(genMs) && (Date.now() - genMs) / 3600000 > limitH) {
    stale.textContent = u.stale(Math.round((Date.now() - genMs) / 3600000));
    stale.hidden = false;
  } else { stale.hidden = true; }
}

async function load() {
  LAST.incidents = (await getJSON("data/incidents.json")) || [];
  LAST.warnings = (await getJSON("data/warnings.json")) || [];
  LAST.summary = await getJSON("data/summary.json");
  LAST.health = await getJSON("data/health.json");
  fillRegions(LAST.incidents, LAST.warnings);
  render();
}

function focusHash() {
  const id = decodeURIComponent((location.hash || "").slice(1));
  if (!id || !map) return;
  const m = markerById[id] || markerById["w:" + id];
  if (m) { map.setView(m.getLatLng(), 10); m.openPopup(); }
}

document.getElementById("lang").addEventListener("click", () => {
  LANG = LANG === "en" ? "tr" : "en";
  try { localStorage.setItem("mw-lang", LANG); } catch (e) {}
  applyI18n(); render();
});
document.getElementById("region").addEventListener("change", e => { REGION = e.target.value; render(); });
window.addEventListener("hashchange", focusHash);

applyI18n();
load().then(focusHash);
setInterval(load, 60000);
