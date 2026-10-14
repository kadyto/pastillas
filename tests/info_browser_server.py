"""Servidor de pruebas con respuestas sintéticas; nunca se incluye en la imagen."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import medicine_info, server, service
from medicine_fixture import fetch, equivalents
medicine_info.fetch_json=fetch
medicine_info.fetch_vademecum=equivalents


class FixtureHandler(server.Handler):
    def api(self, db, path, query):
        if path == '/api/test-medicine-failure' and self.command == 'POST':
            data = self.body()
            user = self.user(db)
            ident = int(data['medication_id'])
            service.owned(db, 'medications', ident, user['id'])
            item = db.execute('SELECT * FROM medicine_links WHERE medication_id=?', (ident,)).fetchone()
            now = int(server.time.time())
            # Conserva la ficha válida, como sucede tras un fallo real del proveedor.
            db.execute('UPDATE medicine_cache SET error=?,attempted_at=?,expires_at=?,pending=0 WHERE cache_key=?',
                       ('CIMA/AEMPS no respondió dentro del tiempo de espera. Se conserva la última información disponible.',
                        now - medicine_info.RETRY_DELAY, now + medicine_info.TTL, medicine_info.info_key(item)))
            db.commit()
            return self.send(200, medicine_info.information(db, ident))
        return super().api(db, path, query)


server.Handler = FixtureHandler
server.main()
