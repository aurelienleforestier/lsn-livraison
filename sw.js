const C='lsn-v4-7-cache-1';
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(C).then(c=>c.addAll(['./manifest.webmanifest'])).catch(()=>{}))});
self.addEventListener('activate',e=>e.waitUntil(Promise.all([clients.claim(),caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==C).map(k=>caches.delete(k))))])));
self.addEventListener('fetch',e=>{
  const req=e.request;
  if(req.mode==='navigate'){
    e.respondWith(fetch(req).then(r=>{const copy=r.clone();caches.open(C).then(c=>c.put(req,copy));return r}).catch(()=>caches.match(req).then(r=>r||caches.match('./'))));
    return;
  }
  e.respondWith(fetch(req).then(r=>{if(req.method==='GET'&&new URL(req.url).origin===location.origin){const copy=r.clone();caches.open(C).then(c=>c.put(req,copy))}return r}).catch(()=>caches.match(req)));
});
