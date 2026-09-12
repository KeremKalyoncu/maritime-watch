/**
 * Maritime Watch Service Worker (Offline PWA Cache)
 * Strategy:
 * - App Shell (HTML, CSS, JS): Cache-First / Stale-While-Revalidate
 * - Data Feeds (/data/*.json): Network-First with Cache-Fallback
 */

const CACHE_NAME = "maritime-watch-shell-v1";
const DATA_CACHE_NAME = "maritime-watch-data-v1";

const STATIC_ASSETS = [
  "./",
  "./index.html",
  "./style.css",
  "./app.js",
  "./manifest.json",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn("[sw] static asset pre-cache warning:", err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME && key !== DATA_CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Handle data JSON requests: Network-First with Cache-Fallback
  if (url.pathname.includes("/data/") && url.pathname.endsWith(".json")) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(DATA_CACHE_NAME).then((cache) => {
              cache.put(event.request, copy);
            });
          }
          return response;
        })
        .catch(() => {
          // Network failed: Serve cached copy
          return caches.match(event.request).then((cached) => {
            if (cached) {
              return cached;
            }
            return new Response(JSON.stringify({ offline: true, error: "no-network" }), {
              headers: { "Content-Type": "application/json" },
            });
          });
        })
    );
    return;
  }

  // Handle static assets & Leaflet CDN: Cache-First
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        // Fetch update in background (Stale-While-Revalidate)
        fetch(event.request).then((response) => {
          if (response && response.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response));
          }
        }).catch(() => {});
        return cached;
      }
      return fetch(event.request).then((response) => {
        if (!response || response.status !== 200 || response.type !== "basic") {
          return response;
        }
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      });
    })
  );
});
