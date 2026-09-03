/* Maritime Watch — static map. Reads data/*.json, refreshes every 60s.
   Degrades gracefully: if the Leaflet CDN is unreachable the timeline and the
   counters still render, with a note where the map would be. */
"use strict";

const COLORS = {
  confirmed: "#e5484d",
  probable: "#f5a524",
  signal: "#8b9bab",
  resolved: "#30a46c",
  "false-positive": "#4b5563",
  warning: "#3b82f6",
};

const TYPE_TR = {
  grounding: "karaya oturma", collision: "çatışma", drift: "sürüklenme",
  distress: "tehlike çağrısı", capsize: "alabora", fire: "yangın",
  sinking: "batma", "man-overboard": "denize adam düştü", unknown: "belirsiz",
};
const STATUS_TR = {
  signal: "zayıf sinyal (doğrulanmadı)", probable: "kuvvetli ihtimal",
  confirmed: "doğrulandı", resolved: "kapandı", "false-positive": "yanlış alarm",
};
const trType = t => TYPE_TR[t] || t;
const trStatus = s => STATUS_TR[s] || s;

const MAP_OK = typeof L !== "undefined";
let map = null;
let layer = null;
const markerById = {};

if (MAP_OK) {
  map = L.map("map", { zoomControl: true }).setView([39.5, 30.5], 6);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: "&copy; OpenStreetMap",
  }).addTo(map);
  L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", {
    maxZoom: 18, opacity: 0.9, attribution: "&copy; OpenSeaMap",
  }).addTo(map);
  layer = L.layerGroup().addTo(map);
} else {
  const el = document.getElementById("map");
  if (el) {
    el.style.display = "flex";
    el.style.alignItems = "center";
    el.style.justifyContent = "center";
    el.style.padding = "24px";
    el.style.textAlign = "center";
    el.style.color = "#93a4b3";
    el.textContent = "Harita kütüphanesi (Leaflet CDN) yüklenemedi — ağ engeli olabilir. "
      + "Zaman çizelgesi ve sayaçlar aşağıda / yanda çalışıyor.";
  }
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

function radiusFor(sev) {
  return { critical: 11, major: 9, minor: 7, info: 6 }[sev] || 7;
}

function incidentPopup(i) {
  const unverified = i.status === "signal"
    ? `<div class="badge-unverified">⚠ Doğrulanmadı — tek zayıf kaynak</div>` : "";
  const orgs = [];
  (i.sources || []).forEach(s => {
    const o = s.org || s.kind;
    if (o && orgs.indexOf(o) === -1) orgs.push(o);
  });
  const srcs = (i.sources || []).map(s => {
    const link = s.url ? ` — <a href="${esc(s.url)}" target="_blank" rel="noopener">bağlantı</a>` : "";
    return `<li>${esc(s.org || s.kind)}: ${esc(s.detail)}${link}</li>`;
  }).join("");
  return `
    <div class="popup-title">${esc(trType(i.type))} — ${esc(trStatus(i.status))}</div>
    ${unverified}
    <div class="popup-meta">
      ${esc(i.area || "konum belirsiz")}
      ${i.casualties ? " · " + i.casualties + " kişi bildirildi" : ""}<br>
      Kaynak: ${esc(orgs.join(", "))}<br>
      İlk görülme: ${fmtTime(i.first_seen)} · Güncelleme: ${fmtTime(i.last_update)}
    </div>
    <ul style="margin:6px 0 0 16px;padding:0">${srcs}</ul>`;
}

function warningPopup(w) {
  const orgs = [];
  (w.sources || []).forEach(s => {
    const o = s.org || s.kind;
    if (o && orgs.indexOf(o) === -1) orgs.push(o);
  });
  if (!orgs.length && w.org) orgs.push(w.org);
  const multi = orgs.length >= 2
    ? `<div class="badge-unverified">✅ ${orgs.length} bağımsız kaynak doğruluyor</div>` : "";
  return `
    <div class="popup-title">🌊 ${esc(w.headline)}</div>
    ${multi}
    <div class="popup-meta">
      ${esc(w.area)} · ${esc(orgs.join(", "))}<br>
      Yayın: ${fmtTime(w.issued)}${w.last_update && w.last_update !== w.issued ? " · Güncelleme: " + fmtTime(w.last_update) : ""}
    </div>
    ${w.url ? `<a href="${esc(w.url)}" target="_blank" rel="noopener">kaynak</a>` : ""}`;
}

function addTimeline(items) {
  const ol = document.getElementById("timeline");
  ol.innerHTML = "";
  items.forEach(it => {
    const li = document.createElement("li");
    li.className = it._kind === "warning" ? "warning" : it.status;
    const when = fmtTime(it._kind === "warning" ? it.issued : it.last_update);
    const title = it._kind === "warning" ? "Uyarı" : trType(it.type);
    const badge = it._kind === "warning" ? "" : trStatus(it.status);
    const area = esc(it.area || "konum belirsiz");
    const src = (it.sources || [])[0];
    const srcHtml = it._kind === "warning"
      ? esc(it.org)
      : (src ? `${esc(src.org || src.kind)}${src.url ? ` — <a href="${esc(src.url)}" target="_blank" rel="noopener">bağlantı</a>` : ""}` : "");
    li.innerHTML = `
      <div class="t-head"><span class="t-type">${esc(title)}</span><span class="t-badge">${badge}</span></div>
      <div class="t-area">${area} · ${when}</div>
      <div class="t-src">${srcHtml}</div>`;
    li.onclick = () => {
      const m = markerById[it._id];
      if (m && map) { map.setView(m.getLatLng(), 9); m.openPopup(); }
    };
    ol.appendChild(li);
  });
}

function drawMarkers(incidents, warnings) {
  if (!MAP_OK) return;
  if (layer) layer.remove();
  layer = L.layerGroup().addTo(map);
  for (const k in markerById) delete markerById[k];

  incidents.forEach(i => {
    if (i.lat == null || i.lon == null) return;
    const color = COLORS[i.status] || COLORS.signal;
    const m = L.circleMarker([i.lat, i.lon], {
      radius: radiusFor(i.severity),
      color,
      weight: i.status === "signal" ? 1 : 2,
      dashArray: i.status === "signal" ? "3 3" : null,
      fillColor: color,
      fillOpacity: i.status === "signal" ? 0.25 : 0.6,
    }).bindPopup(incidentPopup(i));
    m.addTo(layer);
    markerById[i.id] = m;
  });

  warnings.forEach(w => {
    if (w.lat == null || w.lon == null) return;
    const m = L.circleMarker([w.lat, w.lon], {
      radius: 10, color: COLORS.warning, weight: 2, fillColor: COLORS.warning, fillOpacity: 0.15,
    }).bindPopup(warningPopup(w));
    m.addTo(layer);
    markerById["w:" + w.id] = m;
  });
}

async function getJSON(path) {
  try {
    const r = await fetch(path + "?" + Date.now(), { cache: "no-store" });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

async function load() {
  const incidents = (await getJSON("data/incidents.json")) || [];
  const warnings = (await getJSON("data/warnings.json")) || [];
  const summary = await getJSON("data/summary.json");

  drawMarkers(incidents, warnings);

  const tl = []
    .concat(incidents.map(i => ({ ...i, _kind: "incident", _id: i.id })))
    .concat(warnings.map(w => ({ ...w, _kind: "warning", _id: "w:" + w.id })))
    .sort((a, b) => String(b.last_update || b.issued || "").localeCompare(String(a.last_update || a.issued || "")))
    .slice(0, 40);
  addTimeline(tl);

  const meta = document.getElementById("meta");
  const gen = summary ? fmtTime(summary.generated) : "—";
  const bs = summary && summary.by_status
    ? Object.entries(summary.by_status).map(([k, v]) => `${k}: ${v}`).join(" · ")
    : "";
  meta.textContent = `Son güncelleme: ${gen}  ·  ${incidents.length} olay${bs ? " (" + bs + ")" : ""}  ·  ${warnings.length} uyarı`;
}

// open the map focused on #<incident-id> when a deep link is used
function focusHash() {
  const id = decodeURIComponent((location.hash || "").slice(1));
  if (!id || !map) return;
  const m = markerById[id] || markerById["w:" + id];
  if (m) { map.setView(m.getLatLng(), 10); m.openPopup(); }
}
window.addEventListener("hashchange", focusHash);

load().then(focusHash);
setInterval(load, 60000);
