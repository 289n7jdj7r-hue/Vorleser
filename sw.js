/* Service Worker — macht die App offline lauffähig.
   Die App-Dateien kommen immer frisch vom Netz, wenn es eines gibt;
   der Zwischenspeicher dient nur als Rückfall ohne Verbindung.
   Deshalb reicht ab jetzt ein normales Neuladen für Updates. */
const VERSION = 'vorleser-v53';
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
const FRISCH = /(\/|index\.html|sw\.js|manifest\.webmanifest)$/;

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    await c.addAll(KERN);
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
  const url = new URL(e.request.url);
  const eigen = url.origin === location.origin;
  // Fremde Dienste (Bilder-Datenbank, Stimmen, Übersetzung) nie abfangen — nur pdf.js
  if (!eigen && url.hostname !== 'cdnjs.cloudflare.com') return;

  // App-Dateien: Netz zuerst, Zwischenspeicher nur als Rückfall
  if (eigen && FRISCH.test(url.pathname)) {
    e.respondWith((async () => {
      try {
        const antwort = await fetch(e.request, {cache:'no-store'});
        if (antwort.ok) { const c = await caches.open(VERSION); c.put(e.request, antwort.clone()); }
        return antwort;
      } catch (err) {
        return (await caches.match(e.request, {ignoreVary:true})) || caches.match('./index.html');
      }
    })());
    return;
  }

  // Alles andere (Icons, pdf.js): Zwischenspeicher zuerst
  e.respondWith((async () => {
    const treffer = await caches.match(e.request, {ignoreVary:true});
    if (treffer) return treffer;
    try {
      const antwort = await fetch(e.request);
      if (antwort.ok && eigen) { const c = await caches.open(VERSION); c.put(e.request, antwort.clone()); }
      return antwort;
    } catch (err) {
      return eigen ? caches.match('./index.html') : Response.error();
    }
  })());
});
