// Service worker TCShop : garde l'appli en cache pour qu'elle s'ouvre sans réseau (conventions).
// La liste des fichiers et la version sont remplies par tool/make_web.py à chaque construction.
const CACHE = 'tcshop-__VERSION__';
const FILES = __FILES__;

self.addEventListener('install', (e) => {
  // cache: 'reload' : on prend toujours les fichiers frais du PC (jamais une ancienne copie du navigateur)
  e.waitUntil(caches.open(CACHE)
    .then((c) => c.addAll(FILES.map((f) => new Request(f, { cache: 'reload' }))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // les données (stock, synchro) passent toujours par le réseau : jamais de cache
  if (e.request.method !== 'GET' || url.pathname.startsWith('/api/')) return;
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || fetch(e.request).then((resp) => {
      if (resp.ok && url.origin === self.location.origin) {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return resp;
    }).catch(() => caches.match('./', { ignoreSearch: true }))),
  );
});
