"""Las operaciones locales se verifican sin permitir ninguna conexión de red."""
import json
import os
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

from app import android_runtime as mobile, medicine_info, service
from app.db import connect
from app.domain import Invalid, timestamp


class AndroidRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.environment = patch.dict(os.environ)
        self.environment.start();self.addCleanup(self.environment.stop)
        self.network = patch.object(socket, 'socket', side_effect=AssertionError('La operación local no debe abrir sockets'))
        self.network.start();self.addCleanup(self.network.stop)
        self.path = mobile.initialize(self.folder.name, 'Europe/Madrid')

    def call(self, method, path, body=None, status=200):
        result = json.loads(mobile.request(method, '/api' + path, json.dumps(body or {})))
        self.assertEqual(result['status'], status, result)
        return result['body']

    def med(self, **extra):
        now = int(time.time())
        data = dict(name='Tratamiento local', form='Pastillas', unit='pastillas', dose='0.5', stock='12.5',
                    schedule='interval', interval_hours=6, start_at='2026-10-19T08:00:00Z',
                    timezone='Europe/Madrid', expiry_date='2027-05-31')
        data.update(extra)
        return self.call('POST', '/medications', data, 201)['id']

    def test_first_open_and_every_local_operation_work_without_network(self):
        session = self.call('GET', '/session')
        self.assertFalse(session['setup_required'])
        self.assertEqual(session['platform'], 'android')
        self.assertFalse(self.call('GET', '/android/settings')['external_sources'])
        self.assertEqual(self.call('GET', '/version')['state'], 'android')
        recipe = self.call('POST', '/prescriptions', dict(title='Receta local', renewal_date='2026-11-20'), 200)['id']
        ident = self.med(prescription_id=recipe, schedule='as_needed')
        dashboard = self.call('GET', '/dashboard')
        self.assertEqual(dashboard['medications'][0]['stock'], 12.5)
        self.assertEqual(dashboard['medications'][0]['expiry_date'], '2027-05-31')
        self.call('POST', f'/medications/{ident}/stock', dict(kind='purchase', amount='10'))
        self.call('POST', f'/medications/{ident}/doses', dict(status='taken'))
        dashboard = self.call('GET', '/dashboard')
        self.assertEqual(dashboard['medications'][0]['stock'], 22)
        self.call('GET', f'/medications/{ident}/history')
        self.call('GET', '/alerts')
        self.call('GET', '/agenda?day=2026-10-19')
        self.call('POST', '/alerts/read')
        self.assertEqual(json.loads(mobile.export_json())['format'], 'pastillas')
        self.assertEqual(mobile.next_alarm(), 0)
        mobile.tick()
        mobile.check_sources()
        self.call('POST', '/version/check', status=400)
        self.call('POST', '/login', status=400)

    def test_external_queries_require_explicit_opt_in_and_keep_manual_entry_available(self):
        self.call('GET', '/medicine-search?q=prueba', status=409)
        self.med(schedule='as_needed')
        self.call('PUT', '/android/settings', dict(external_sources=True))
        with patch.object(medicine_info, 'search', return_value={'results': []}) as search:
            self.call('GET', '/medicine-search?q=prueba')
            search.assert_called_once_with('prueba', 1)
        self.call('PUT', '/android/settings', dict(external_sources=False))
        self.call('GET', '/medicine-search?q=prueba', status=409)
        self.assertEqual(len(self.call('GET', '/dashboard')['medications']), 1)

    def test_restart_keeps_sqlite_data_and_deducts_missed_scheduled_doses_only_once(self):
        now = int(time.time())
        ident = self.med()
        with connect() as db:
            db.execute('UPDATE medications SET start_at=?,auto_cursor=? WHERE id=?', (now - 13*3600, now - 13*3600, ident))
        mobile.initialize(self.folder.name)
        mobile.tick(now=now)
        with connect() as db:
            med = db.execute('SELECT * FROM medications WHERE id=?', (ident,)).fetchone()
            self.assertEqual(med['stock'], 11500)
            self.assertEqual(db.execute('SELECT count(*) FROM doses').fetchone()[0], 2)
        mobile.tick(now=now)
        with connect() as db:
            self.assertEqual(db.execute('SELECT stock FROM medications WHERE id=?', (ident,)).fetchone()[0], 11500)
        self.assertEqual(mobile.next_alarm(now), now + 5*3600)

    def test_import_merges_remaps_history_and_is_atomic_and_deduplicated(self):
        ident = self.med(schedule='as_needed')
        self.call('POST', f'/medications/{ident}/doses', dict(status='taken'))
        exported = mobile.export_json()
        result = json.loads(mobile.import_json(exported))
        self.assertEqual(result['medications'], 1)
        self.assertEqual(result['doses'], 1)
        meds = self.call('GET', '/dashboard')['medications']
        self.assertEqual([m['stock'] for m in meds], [12, 12])
        with connect() as db:
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
        with self.assertRaisesRegex(Invalid, 'ya se ha importado'):
            mobile.import_json(exported)
        invalid = json.loads(exported)
        invalid['medications'][0]['name'] = 'No debe insertarse'
        invalid['doses'][0]['status'] = 'invalid'
        with self.assertRaises(Invalid):
            mobile.import_json(json.dumps(invalid))
        self.assertEqual(len(self.call('GET', '/dashboard')['medications']), 2)

    def test_export_is_a_consistent_snapshot_when_a_dose_is_recorded_during_export(self):
        ident = self.med(schedule='as_needed')
        changed = False
        def connection_with_concurrent_write():
            db = connect()
            def before_query(sql):
                nonlocal changed
                if not changed and sql.startswith('SELECT * FROM prescriptions'):
                    changed = True
                    with connect() as writer:
                        service.record_dose(writer, mobile.local_user(writer)['id'], ident, dict(status='taken'))
            db.set_trace_callback(before_query)
            return db
        with patch.object(mobile, 'connect', side_effect=connection_with_concurrent_write):
            exported = json.loads(mobile.export_json())
        self.assertTrue(changed)
        self.assertEqual(exported['medications'][0]['stock'], 12500)
        self.assertEqual(exported['doses'], [])
        self.assertEqual(self.call('GET', '/dashboard')['medications'][0]['stock'], 12)

    def test_import_preserves_expiry_links_and_does_not_query_sources(self):
        ident = self.med(schedule='as_needed')
        with connect() as db:
            db.execute('INSERT INTO medicine_links VALUES(?,?,?,?,?,?)', (ident, '', '99999', '999001', 'Nombre CIMA', 'Envase'))
        mobile.import_json(mobile.export_json())
        self.call('GET', '/session')
        mobile.check_sources()
        with connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM medicine_links').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT count(*) FROM medicine_cache').fetchone()[0], 0)

    def test_import_preserves_daily_clock_cutoff_and_adapts_older_copies(self):
        today = timestamp('2026-10-25T22:40:00Z')
        cutoff = timestamp('2026-10-25T23:00:00Z')
        with patch('time.time', return_value=today):
            ident = self.med(interval_hours=24, start_at='2026-10-24T21:30:00Z')
            with connect() as db:
                db.execute('UPDATE medications SET daily_from=? WHERE id=?', (cutoff, ident))
                user = mobile.local_user(db)
                service.record_dose(db, user['id'], ident, dict(scheduled_at=timestamp('2026-10-25T21:30:00Z')), today)
            exported = json.loads(mobile.export_json())
            mobile.import_json(json.dumps(exported))
            self.assertEqual(self.call('GET', '/dashboard')['medications'][1]['daily_from'], cutoff)
            del exported['medications'][0]['daily_from']
            mobile.import_json(json.dumps(exported))
            with connect() as db:
                meds = db.execute('SELECT * FROM medications ORDER BY id').fetchall()
                self.assertEqual([m['daily_from'] for m in meds], [cutoff, cutoff, cutoff])
                self.assertEqual([m['stock'] for m in meds], [12000, 12000, 12000])
            self.assertEqual(mobile.next_alarm(today), timestamp('2026-10-26T22:30:00Z'))

    def test_erase_requires_confirmation_and_removes_all_personal_records(self):
        self.med(schedule='as_needed')
        self.call('POST', '/android/erase', status=400)
        self.assertEqual(len(self.call('GET', '/dashboard')['medications']), 1)
        self.call('POST', '/android/erase', dict(confirm='BORRAR'))
        self.assertEqual(self.call('GET', '/dashboard')['medications'], [])
        self.assertFalse(self.call('GET', '/android/settings')['external_sources'])

    def test_native_transport_rejects_other_urls_and_malformed_input(self):
        for method, path, body in [('GET', 'https://example.com', '{}'), ('GET', '/index.html', '{}'),
                                   ('PATCH', '/api/session', '{}'), ('POST', '/api/medications', '[]'),
                                   ('POST', '/api/medications', '{"stock":NaN}')]:
            self.assertEqual(json.loads(mobile.request(method, path, body))['status'], 400)


if __name__ == '__main__':
    unittest.main()
