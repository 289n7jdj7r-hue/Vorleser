/* Service Worker — macht die App offline lauffähig.
   Version hochzählen, wenn du index.html änderst. */
const VERSION = 'vorleser-v31';
const KERN = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icon-192.png',
  './icon-512.png',
  './apple-touch-icon.png',
  './favicon.png'
];
const PDFJS = [
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js'
];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    await c.addAll(KERN);
    // pdf.js darf fehlschlagen, ohne die Installation zu kippen
    await Promise.allSettled(PDFJS.map(u => c.add(new Request(u, {mode:'cors'}))));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const namen = await caches.keys();
    await Promise.all(namen.filter(n => n !== VERSION).map(n => caches.delete(n)));
    self.clients.claim();
  })());
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith((async () => {
    const treffer = await caches.match(e.request, {ignoreVary:true});
    if (treffer) return treffer;
    try {
      const antwort = await fetch(e.request);
      if (antwort.ok && new URL(e.request.url).origin === location.origin) {
        const c = await caches.open(VERSION);
        c.put(e.request, antwort.clone());
      }
      return antwort;
    } catch (err) {
      return caches.match('./index.html');
    }
  })());
});
