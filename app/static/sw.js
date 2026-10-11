// Solo facilita notificaciones mientras se consulta la app. No almacena datos médicos.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(async clients => {
    for (const client of clients) {
      if ('focus' in client) { await client.focus(); return; }
    }
    return self.clients.openWindow('/');
  }));
});
