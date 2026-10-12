import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import auth, domain, service
from app.db import connect, initialize
from test_pastillas import DatabaseTests, NOW


class ExpiryTests(DatabaseTests):
    def test_date_is_optional_for_scheduled_and_as_needed_medications(self):
        for schedule in ('interval', 'as_needed'):
            med = self.med(schedule=schedule)
            self.assertIsNone(med['expiry_date'])
        dated = self.med(schedule='as_needed', expiry_date='2027-05-31')
        self.assertEqual(dated['expiry_date'], '2027-05-31')
        self.assertEqual(domain.serialize_med(dated, NOW)['expiry_date'], '2027-05-31')
        exported = service.export_data(self.db, self.user)
        self.assertEqual(next(m for m in exported['medications'] if m['id'] == dated['id'])['expiry_date'], '2027-05-31')

    def test_invalid_dates_are_rejected_before_saving(self):
        for value in ('2027-02-29', '2026-13-01', '31/05/2027', '1999-12-31', '2101-01-01', 123, True):
            with self.subTest(value=value), self.assertRaisesRegex(domain.Invalid, 'Fecha de caducidad'):
                self.med(schedule='as_needed', expiry_date=value)
        self.assertEqual(self.db.execute('SELECT count(*) FROM medications').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM stock_movements').fetchone()[0], 0)

    def test_edit_omission_preserves_date_and_explicit_empty_clears_it(self):
        med = self.med(schedule='as_needed', expiry_date='2027-05-31')
        body = dict(name=med['name'], schedule='as_needed', start_at='2026-10-11T08:00:00Z', dose='0.5')
        service.medication_save(self.db, self.user, body, med['id'], NOW)
        self.assertEqual(service.owned(self.db, 'medications', med['id'], self.user_id)['expiry_date'], '2027-05-31')
        for value in ('2028-02-29', '', None):
            service.medication_save(self.db, self.user, dict(body, expiry_date=value), med['id'], NOW)
            stored = service.owned(self.db, 'medications', med['id'], self.user_id)
            self.assertEqual(stored['expiry_date'], value or None)
            self.assertEqual(stored['stock'], med['stock'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM stock_movements').fetchone()[0], 1)

    def test_date_survives_restart_and_does_not_consume_as_needed_stock(self):
        med = self.med(schedule='as_needed', expiry_date='2026-10-01')
        self.db.close()
        initialize(self.path)
        self.db = connect(self.path)
        data = service.dashboard(self.db, self.user, NOW)
        self.assertEqual(data['medications'][0]['expiry_date'], '2026-10-01')
        self.assertEqual(data['medications'][0]['stock'], med['stock'] / domain.SCALE)
        self.assertEqual(data['agenda'], [])


class ExpiryMigrationTests(unittest.TestCase):
    def test_version_three_migration_preserves_all_records_and_backup_on_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'pastillas.sqlite')
            initialize(path)
            with connect(path) as db:
                uid = service.create_user(db, dict(username='ana', password='contrasena-larga-123'))
                user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
                rx = service.insert(db, 'prescriptions', dict(user_id=uid, title='Receta conservada'))
                ident = service.medication_save(db, user, dict(name='Paracetamol', dose=1, stock=20,
                    schedule='as_needed', start_at='2026-10-11T08:00:00Z', prescription_id=rx), now=NOW)
                service.record_dose(db, uid, ident, {}, NOW)
                service.stock_add(db, uid, ident, dict(kind='verification', amount=19), NOW)
                auth.session(db, uid)
                service.insert(db, 'medicine_links', dict(medication_id=ident, nregistro='65476', cima_name='Conservado'))
                db.execute('ALTER TABLE medications DROP COLUMN expiry_date')
                db.execute('PRAGMA user_version=3')
                tables = ('users', 'sessions', 'prescriptions', 'medications', 'doses', 'stock_movements', 'medicine_links')
                before = {table: [dict(row) for row in db.execute(f'SELECT * FROM {table}')] for table in tables}
            initialize(path)
            initialize(path)
            with connect(path) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 4)
                for table in tables:
                    after = [dict(row) for row in db.execute(f'SELECT * FROM {table}')]
                    if table == 'medications':
                        self.assertTrue(all(row.pop('expiry_date') is None for row in after))
                    self.assertEqual(after, before[table])
                db.execute('UPDATE medications SET expiry_date=? WHERE id=?', ('2027-05-31', ident))
            initialize(path)
            with connect(path) as db:
                self.assertEqual(db.execute('SELECT expiry_date FROM medications').fetchone()[0], '2027-05-31')
            with sqlite3.connect(path + '.pre-v4.sqlite') as backup:
                backup.row_factory = sqlite3.Row
                self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 3)
                self.assertEqual([dict(row) for row in backup.execute('SELECT * FROM medications')], before['medications'])


if __name__ == '__main__':
    unittest.main()
