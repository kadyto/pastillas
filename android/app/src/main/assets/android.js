/* Transporte en memoria. Ninguna petición /api sale del dispositivo. */
(() => {
  'use strict';
  if (!window.AndroidBridge) return;
  let serial = 0;
  const pending = new Map();
  const originalFetch = window.fetch.bind(window);
  window.PastillasNative = {
    resolve(id, serialized) {
      const task = pending.get(id);
      if (!task) return;
      pending.delete(id);clearTimeout(task.timer);
      try {
        const response = JSON.parse(serialized);
        task.resolve(new Response(JSON.stringify(response.body), {status: response.status, headers: {'Content-Type': 'application/json; charset=utf-8'}}));
      } catch { task.reject(new Error('No se pudo leer la respuesta local.')); }
    },
    status() { return JSON.parse(AndroidBridge.status()); },
    action(name) { AndroidBridge.action(name); },
    setReminders(value) { AndroidBridge.setReminders(value); },
  };
  window.fetch = (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return originalFetch(input, options);
    const id = String(++serial);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {pending.delete(id);reject(new Error('La operación está tardando más de lo esperado. Los datos locales se conservan.'));}, 120000);
      pending.set(id, {resolve, reject, timer});
      AndroidBridge.request(id, options.method || 'GET', url.pathname + url.search, options.body || '{}');
    });
  };
  document.addEventListener('click', event => {
    const anchor = event.target.closest('a[href]');
    if (!anchor) return;
    const url = new URL(anchor.href, location.href);
    if (url.origin !== location.origin) {event.preventDefault();if(url.protocol === 'https:') AndroidBridge.openUrl(url.href);}
    if (url.pathname === '/api/export') {event.preventDefault();AndroidBridge.action('export');}
  });
})();
