/* LocalOCR service worker — app-shell offline + push.
 * Vanilla, no build step. Bump CACHE_VERSION on any shell change. */

'use strict';

const CACHE_VERSION = 'localocr-v1';
const OFFLINE_URL = '/offline.html';

/* Explicit app-shell precache list for the landing page at "/".
 * NO wildcards — every file needed to render "/" offline is named here.
 * If you change the landing page's assets, update this list AND bump
 * CACHE_VERSION above. */
const APP_SHELL = [
  '/',
  OFFLINE_URL,
  '/manifest.webmanifest',
  '/icon-192.png',
  '/icon-512.png',
  '/icon-512-maskable.png',
  '/apple-touch-icon.png',
  '/design/marketing/vendor/motion.min.js',
  '/design/marketing/fonts/instrument-serif-400.woff2',
  '/design/marketing/fonts/instrument-serif-400-italic.woff2',
  '/design/marketing/fonts/albert-sans-400.woff2',
  '/design/marketing/fonts/albert-sans-600.woff2',
  '/design/marketing/fonts/spline-sans-mono-400.woff2',
  '/design/marketing/fonts/spline-sans-mono-700.woff2'
];

/* ---- install: precache the shell ---- */
/* Note: no skipWaiting() here — an updated worker stays "waiting" so the page
 * can show its "Update available — reload" prompt. The page posts SKIP_WAITING
 * (see message handler below) when the user clicks reload. */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(APP_SHELL))
  );
});

/* ---- message: page asks the waiting worker to activate now ---- */
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

/* ---- activate: drop old caches, take control ---- */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

/* ---- fetch: navigations = network-first w/ cache+offline fallback;
 *            shell assets  = cache-first ---- */
self.addEventListener('fetch', (event) => {
  const request = event.request;

  // Only handle same-origin GET; let everything else pass through.
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) {
    return;
  }

  // Navigations (page loads): network-first, fall back to cache, then offline page.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() =>
          caches.match(request).then((cached) => cached || caches.match(OFFLINE_URL))
        )
    );
    return;
  }

  // Static shell assets: cache-first, fall back to network (and cache the result).
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response && response.status === 200 && response.type === 'basic') {
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});

/* ---- push: show a notification from the payload ---- */
self.addEventListener('push', (event) => {
  let data = {};
  if (event.data) {
    try { data = event.data.json(); }
    catch (e) { data = { title: 'LocalOCR', body: event.data.text() }; }
  }
  const title = data.title || 'LocalOCR';
  const options = {
    body: data.body || 'You have a new notification.',
    icon: data.icon || '/icon-192.png',
    badge: data.badge || '/icon-192.png',
    data: { url: data.url || '/' },
    tag: data.tag || 'localocr'
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

/* ---- notificationclick: focus an open tab or open a new one ---- */
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(targetUrl);
    })
  );
});
