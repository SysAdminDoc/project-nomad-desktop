const CACHE_NAME = 'nomad-v1';

const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/css/app.css',
  '/static/css/premium.css',
  '/static/logo.png',
  '/static/maplibre-gl.js',
  '/static/maplibre-gl.css',
  '/static/pmtiles.js',
  '/static/js/epub.min.js'
];

// Cache static assets on install
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Clean up old caches on activate
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Network-first for API calls
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Cache-first for static assets
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        return cached || fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        });
      })
    );
    return;
  }

  // Offline fallback for index page
  if (url.pathname === '/' || url.pathname === '/index.html') {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match('/'))
    );
    return;
  }

  // Default: network with cache fallback
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});

// Handle push-alert messages from the main page for background notifications
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'push-alert') {
    self.registration.showNotification(event.data.title || 'N.O.M.A.D. Alert', {
      body: event.data.body || 'New alert received',
      icon: '/static/logo.png',
      badge: '/static/logo.png',
      tag: 'nomad-alert',
      renotify: true,
      requireInteraction: true,
    });
  }
});

// Handle notification click — focus the app window
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(clients => {
      if (clients.length > 0) {
        return clients[0].focus();
      }
      return self.clients.openWindow('/');
    })
  );
});
