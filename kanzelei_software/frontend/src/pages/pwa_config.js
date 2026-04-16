// ============================================================
// KANZLEI AI — PWA MANIFEST
// Datei: public/manifest.json
// Macht die App installierbar auf iOS, Android, Desktop
// ============================================================

// INHALT FÜR public/manifest.json:
export const MANIFEST = {
  "short_name": "Kanzlei AI",
  "name": "Kanzlei AI — Steuerberater Suite",
  "description": "KI-gestütztes Kanzlei-Management für Steuerberater",
  "icons": [
    { "src": "favicon.ico",   "sizes": "64x64 32x32 24x24 16x16", "type": "image/x-icon" },
    { "src": "logo192.png",   "type": "image/png", "sizes": "192x192" },
    { "src": "logo512.png",   "type": "image/png", "sizes": "512x512", "purpose": "any maskable" }
  ],
  "start_url": ".",
  "display": "standalone",
  "theme_color": "#0b0d11",
  "background_color": "#0b0d11",
  "orientation": "portrait-primary",
  "categories": ["business", "finance", "productivity"],
  "lang": "de",
  "scope": "/",
  "shortcuts": [
    {
      "name": "Dashboard",
      "short_name": "Dashboard",
      "url": "/?tab=dashboard",
      "icons": [{ "src": "logo192.png", "sizes": "192x192" }]
    },
    {
      "name": "KI-Assistent",
      "short_name": "KI Chat",
      "url": "/?tab=ki",
      "icons": [{ "src": "logo192.png", "sizes": "192x192" }]
    },
    {
      "name": "Mandanten",
      "short_name": "Mandanten",
      "url": "/?tab=mandanten",
      "icons": [{ "src": "logo192.png", "sizes": "192x192" }]
    }
  ]
};

// ============================================================
// SERVICE WORKER (public/sw.js)
// Offline-Funktionalität + Push-Notifications
// ============================================================

export const SERVICE_WORKER = `
const CACHE_NAME = 'kanzlei-ai-v2';
const STATIC_ASSETS = [
  '/',
  '/static/js/main.chunk.js',
  '/static/css/main.chunk.css',
  '/manifest.json',
];

// Install: Cache statische Assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate: Alte Caches löschen
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch: Cache-First für Assets, Network-First für API
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API-Anfragen immer direkt (nie aus Cache)
  if (url.pathname.startsWith('/api/') || url.port === '8000') {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (response.ok && event.request.method === 'GET') {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clone);
          });
        }
        return response;
      }).catch(() => {
        // Offline-Fallback
        if (event.request.destination === 'document') {
          return caches.match('/');
        }
      });
    })
  );
});

// Push-Notifications
self.addEventListener('push', (event) => {
  const data = event.data?.json() || {};
  const options = {
    body:    data.body    || 'Neue Benachrichtigung von Kanzlei AI',
    icon:    '/logo192.png',
    badge:   '/logo192.png',
    vibrate: [200, 100, 200],
    data:    { url: data.url || '/' },
    actions: [
      { action: 'open',    title: 'Öffnen' },
      { action: 'dismiss', title: 'Schließen' },
    ],
  };
  event.waitUntil(
    self.registration.showNotification(
      data.title || 'Kanzlei AI',
      options
    )
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action === 'open' || !event.action) {
    event.waitUntil(
      clients.openWindow(event.notification.data?.url || '/')
    );
  }
});
`;