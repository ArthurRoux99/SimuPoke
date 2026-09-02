/* SimuPoke — service worker : rend l'app installable et **hors-ligne**.
 *
 * Stratégie cache-first avec remplissage à l'usage : après une première visite
 * en ligne, tout (coquille de l'app, runtime Pyodide, wheel, données) est en
 * cache → l'app fonctionne sans réseau. Les appels /api/* ne passent jamais ici
 * (le shim de fetch de bootstrap.js les résout dans la page).
 */
const CACHE = 'simupoke-v1';
const CORE = [
  './', './index.html', './bootstrap.js',
  './static/app.js', './static/style.css',
  './manifest.webmanifest', './manifest.json',
  './icon-192.png', './icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(CORE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const sameOrigin = url.origin === location.origin;
  const isPyodide = url.hostname === 'cdn.jsdelivr.net';
  if (!sameOrigin && !isPyodide) return;   // laisse passer le reste

  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const hit = await cache.match(req);
    if (hit) return hit;
    try {
      const res = await fetch(req);
      if (res && (res.ok || res.type === 'opaque')) cache.put(req, res.clone());
      return res;
    } catch (err) {
      const fallback = await cache.match(req);
      if (fallback) return fallback;
      throw err;
    }
  })());
});
