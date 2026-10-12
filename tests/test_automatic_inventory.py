import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app import alerts, inventory, service
from app.db import connect, initialize
from test_pastillas import DatabaseTests, NOW


class AutomaticInventoryTests(DatabaseTests):
    def stock(self,ident):
        return self.db.execute('SELECT stock FROM medications WHERE id=?',(ident,)).fetchone()[0]

    def sync(self,when=NOW):
        inventory.sync_due(self.db,when)

    def test_scheduled_doses_reduce_stock_without_confirmation_and_are_idempotent(self):
        med=self.med(stock=10,dose='0.5')
        self.sync();self.sync();self.sync(NOW+86400)
        self.assertEqual(self.stock(med['id']),8000) # inicio, +8h, +16h, +24h
        rows=self.db.execute('SELECT * FROM doses').fetchall()
        self.assertEqual(len(rows),4)
        self.assertTrue(all(r['automatic'] for r in rows))
        self.assertEqual(self.db.execute('SELECT sum(amount) FROM stock_movements').fetchone()[0],8000)

    def test_restart_and_simultaneous_worker_or_dashboard_do_not_duplicate(self):
        med=self.med(stock=10)
        def sync(_):
            with connect(self.path) as db: inventory.sync_due(db,NOW+86400)
        with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(sync,range(5)))
        with connect(self.path) as db:inventory.sync_due(db,NOW+86400)
        self.assertEqual(self.stock(med['id']),8000)
        self.assertEqual(self.db.execute('SELECT count(*) FROM doses').fetchone()[0],4)

    def test_offline_recovery_handles_more_than_one_thousand_slots(self):
        med=self.med(stock=2000,dose=1,interval_hours=1)
        self.sync(NOW+1200*3600)
        self.assertEqual(self.stock(med['id']),799000)
        self.assertEqual(self.db.execute('SELECT count(*) FROM doses').fetchone()[0],1201)

    def test_manual_and_future_takes_are_not_subtracted_twice(self):
        med=self.med(start_at='2026-10-11T08:01:00Z',dose=1,stock=10)
        service.record_dose(self.db,self.user_id,med['id'],dict(scheduled_at=NOW+60),NOW)
        self.db.commit();self.sync(NOW+60);self.sync(NOW+120)
        self.assertEqual(self.stock(med['id']),9000)
        self.assertEqual(self.db.execute('SELECT count(*) FROM doses').fetchone()[0],1)

    def test_omitting_an_assumed_take_returns_stock_once_and_stays_omitted(self):
        med=self.med();self.sync()
        self.assertEqual(self.stock(med['id']),10000)
        service.record_dose(self.db,self.user_id,med['id'],dict(scheduled_at=NOW,status='skipped'),NOW+1)
        self.db.commit();self.sync(NOW+2)
        service.record_dose(self.db,self.user_id,med['id'],dict(scheduled_at=NOW,status='skipped'),NOW+3)
        self.assertEqual(self.stock(med['id']),10500)
        self.assertEqual(self.db.execute('SELECT status FROM doses').fetchone()[0],'skipped')
        self.assertEqual(self.db.execute('SELECT sum(amount) FROM stock_movements').fetchone()[0],10500)

    def test_undo_scheduled_dose_does_not_reappear_after_restart(self):
        med=self.med();self.sync()
        dose=self.db.execute('SELECT id FROM doses').fetchone()[0]
        service.undo_dose(self.db,self.user_id,dose,NOW+1);self.db.commit()
        with connect(self.path) as db:inventory.sync_due(db,NOW+120)
        self.assertEqual(self.stock(med['id']),10500)

    def test_as_needed_requires_manual_record_and_manual_undo_still_works(self):
        med=self.med(schedule='as_needed');self.sync(NOW+30*86400)
        self.assertEqual(self.stock(med['id']),10500)
        self.assertEqual(self.db.execute('SELECT count(*) FROM doses').fetchone()[0],0)
        dose=service.record_dose(self.db,self.user_id,med['id'],{},NOW)
        service.undo_dose(self.db,self.user_id,dose,NOW)
        self.assertEqual(self.stock(med['id']),10500)
        self.assertEqual(self.db.execute('SELECT count(*) FROM doses').fetchone()[0],0)

    def test_pause_resume_and_schedule_edit_do_not_rewrite_past_consumption(self):
        med=self.med(stock=20)
        data=dict(name=med['name'],dose=1,form=med['form'],unit=med['unit'],schedule='interval',interval_hours=8,
                  start_at='2026-10-11T08:00:00Z',active=False)
        service.medication_save(self.db,self.user,data,med['id'],now=NOW+9*3600);self.db.commit()
        self.assertEqual(self.stock(med['id']),19000) # dos descuentos antiguos de 0,5
        self.sync(NOW+3*86400)
        self.assertEqual(self.stock(med['id']),19000)
        data['active']=True
        service.medication_save(self.db,self.user,data,med['id'],now=NOW+3*86400);self.db.commit()
        self.sync(NOW+3*86400+8*3600)
        self.assertEqual(self.stock(med['id']),18000)
        self.assertEqual(self.db.execute('SELECT expected_amount FROM doses ORDER BY scheduled_at').fetchall()[0][0],500)

    def test_ended_course_stops_consuming_but_recovers_due_doses_to_end(self):
        med=self.med(end_at='2026-10-11T16:00:00Z')
        self.sync(NOW+5*86400)
        self.assertEqual(self.stock(med['id']),9500)
        self.assertEqual(self.db.execute('SELECT count(*) FROM doses').fetchone()[0],2)

    def test_future_course_and_past_start_do_not_consume_before_current_inventory(self):
        med=self.med(start_at='2026-10-10T08:00:00Z',dose=1,stock=10)
        self.sync(NOW)
        self.assertEqual(self.stock(med['id']),9000) # solo la toma actual; stock introducido hoy
        future=self.med(start_at='2026-10-12T08:00:00Z',stock=10)
        self.sync(NOW)
        self.assertEqual(self.stock(future['id']),10000)

    def test_stock_shortage_never_creates_negative_stock_or_fake_reimbursement(self):
        med=self.med(dose=1,stock='0.25');self.sync()
        row=self.db.execute('SELECT * FROM doses').fetchone()
        self.assertEqual((row['amount'],row['expected_amount']),(250,1000))
        self.assertEqual(self.stock(med['id']),0)
        item=service.agenda(self.db,self.user,'2026-10-11',NOW)[0]
        self.assertEqual(item['stock_shortfall'],0.75)
        service.record_dose(self.db,self.user_id,med['id'],dict(scheduled_at=NOW,status='skipped'),NOW+1)
        self.assertEqual(self.stock(med['id']),250)

    def test_verification_compares_current_stock_and_records_even_no_difference(self):
        med=self.med(stock=10)
        service.stock_add(self.db,self.user_id,med['id'],dict(kind='verification',amount='9.5',note='Contado'),NOW)
        self.db.commit();self.sync(NOW+1)
        self.assertEqual(self.stock(med['id']),9500)
        record=self.db.execute("SELECT * FROM stock_movements WHERE kind='verification'").fetchone()
        self.assertEqual(record['amount'],0)
        self.assertEqual(self.db.execute('SELECT stock_verified_at FROM medications').fetchone()[0],NOW)
        service.stock_add(self.db,self.user_id,med['id'],dict(kind='verification',amount=10),NOW+2)
        self.db.commit();self.sync(NOW+3)
        self.assertEqual(self.stock(med['id']),10000)
        self.assertEqual(self.db.execute('SELECT sum(amount) FROM stock_movements').fetchone()[0],10000)

    def test_purchase_after_offline_recovery_does_not_consume_new_stock_for_old_missing_takes(self):
        med=self.med(stock=0,dose=1)
        service.stock_add(self.db,self.user_id,med['id'],dict(amount=10),NOW+86400)
        self.db.commit();self.sync(NOW+86400+1)
        self.assertEqual(self.stock(med['id']),10000)
        self.sync(NOW+86400+8*3600)
        self.assertEqual(self.stock(med['id']),9000)

    def test_daily_doses_and_dst_duplicate_clocks_consume_once(self):
        med=self.med(start_at='2026-03-29T00:00:00Z',schedule='daily',times=['02:30','03:30'],timezone='Europe/Madrid',stock=10,dose=1)
        self.db.execute('UPDATE medications SET auto_cursor=? WHERE id=?',(1774742399,med['id']));self.db.commit()
        self.sync(1774828799)
        self.assertEqual(self.stock(med['id']),9000)
        self.assertEqual(self.db.execute('SELECT count(*) FROM doses').fetchone()[0],1)

    def test_automatic_consumption_keeps_reminders_and_dedupe(self):
        med=self.med();self.sync()
        alerts.generate(self.db,NOW+1);alerts.generate(self.db,NOW+20)
        self.assertEqual(self.db.execute("SELECT count(*) FROM alerts WHERE kind='dose'").fetchone()[0],1)
        service.record_dose(self.db,self.user_id,med['id'],dict(scheduled_at=NOW,status='skipped'),NOW+21)
        self.db.execute("DELETE FROM alerts WHERE kind='dose'");self.db.commit()
        alerts.generate(self.db,NOW+22)
        self.assertEqual(self.db.execute("SELECT count(*) FROM alerts WHERE kind='dose'").fetchone()[0],0)

    def test_user_scope_keeps_other_users_inventory_private(self):
        med=self.med();inventory.sync_due(self.db,NOW,self.other_id)
        self.assertEqual(self.stock(med['id']),10500)
        with self.assertRaises(service.NotFound):
            service.stock_add(self.db,self.other_id,med['id'],dict(kind='verification',amount=4),NOW)


class AutomaticMigrationTests(unittest.TestCase):
    def test_version_two_preserves_stock_and_ledger_without_retroactive_consumption(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'db.sqlite');initialize(path)
            with connect(path) as db:
                uid=service.create_user(db,dict(username='ana',password='contrasena-larga-123'))
                user=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                ident=service.medication_save(db,user,dict(name='Conservado',form='Pastillas',unit='pastillas',dose=1,stock=40,
                      schedule='interval',interval_hours=8,start_at='2026-10-01T08:00:00Z'),now=NOW)
                db.execute('ALTER TABLE medications DROP COLUMN auto_cursor');db.execute('ALTER TABLE medications DROP COLUMN stock_verified_at')
                db.execute('ALTER TABLE doses DROP COLUMN automatic');db.execute('ALTER TABLE doses DROP COLUMN expected_amount')
                db.execute('ALTER TABLE medications DROP COLUMN expiry_date')
                db.execute('PRAGMA user_version=2')
            with patch('app.db.time.time',return_value=NOW):initialize(path)
            initialize(path)
            with connect(path) as db:
                inventory.sync_due(db,NOW)
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)
                self.assertEqual(db.execute('SELECT stock FROM medications').fetchone()[0],40000)
                self.assertEqual(db.execute('SELECT count(*) FROM doses').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT sum(amount) FROM stock_movements').fetchone()[0],40000)
                inventory.sync_due(db,NOW+8*3600)
                self.assertEqual(db.execute('SELECT stock FROM medications').fetchone()[0],39000)
            with sqlite3.connect(path+'.pre-v3.sqlite') as backup:
                self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0],2)
                self.assertEqual(backup.execute('SELECT stock FROM medications').fetchone()[0],40000)
