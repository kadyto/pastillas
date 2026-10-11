import hashlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from email.message import Message
from unittest.mock import patch

from app import alerts, auth, domain, service
from app.db import connect, initialize
from app.server import Handler, Forbidden, Unauthorized

NOW = int(datetime.fromisoformat("2026-10-11T08:00:00+00:00").timestamp())


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = self.folder.name + "/test.sqlite"
        initialize(self.path)
        self.db = connect(self.path)
        self.user_id = service.create_user(self.db, dict(username="ana", password="contrasena-larga-123"))
        self.other_id = service.create_user(self.db, dict(username="bea", password="otra-contrasena-123"))
        self.db.execute("UPDATE users SET admin=1 WHERE id=?", (self.user_id,))
        self.db.commit()
        self.user = self.db.execute("SELECT * FROM users WHERE id=?", (self.user_id,)).fetchone()

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def med(self, **overrides):
        data = dict(name="Mi medicamento", form="Pastillas", unit="pastillas", dose="0.5", stock="10.5",
                    schedule="interval", interval_hours=8, start_at="2026-10-11T08:00:00Z")
        data.update(overrides)
        ident = service.medication_save(self.db, self.user, data, now=NOW)
        self.db.commit()
        return service.owned(self.db, "medications", ident, self.user_id)


class InventoryTests(DatabaseTests):
    def test_fractional_dose_is_atomic_and_idempotent(self):
        med = self.med()
        first = service.record_dose(self.db, self.user_id, med["id"], dict(scheduled_at=NOW), NOW)
        second = service.record_dose(self.db, self.user_id, med["id"], dict(scheduled_at=NOW), NOW)
        self.assertEqual(first, second)
        self.assertEqual(self.db.execute("SELECT stock FROM medications").fetchone()[0], 10000)
        self.assertEqual(self.db.execute("SELECT count(*) FROM doses").fetchone()[0], 1)
        service.undo_dose(self.db, self.user_id, first)
        self.assertEqual(self.db.execute("SELECT stock FROM medications").fetchone()[0], 10500)
        total = self.db.execute("SELECT sum(amount) FROM stock_movements").fetchone()[0]
        self.assertEqual(total, 10500)
        with self.assertRaises(service.NotFound):
            service.undo_dose(self.db, self.user_id, first)

    def test_skipped_dose_does_not_consume_and_status_cannot_overwrite(self):
        med = self.med()
        service.record_dose(self.db, self.user_id, med["id"], dict(scheduled_at=NOW, status="skipped"), NOW)
        self.assertEqual(self.db.execute("SELECT stock FROM medications").fetchone()[0], 10500)
        with self.assertRaises(service.Conflict):
            service.record_dose(self.db, self.user_id, med["id"], dict(scheduled_at=NOW), NOW)

    def test_insufficient_stock_cannot_create_dose(self):
        med = self.med(stock="0.25")
        with self.assertRaises(service.Conflict):
            service.record_dose(self.db, self.user_id, med["id"], dict(scheduled_at=NOW), NOW)
        self.assertEqual(self.db.execute("SELECT count(*) FROM doses").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT stock FROM medications").fetchone()[0], 250)

    def test_purchase_and_physical_count_have_correct_ledger(self):
        med = self.med(form="Jarabe", unit="ml", dose=5, stock=100)
        service.stock_add(self.db, self.user_id, med["id"], dict(amount=200, price="8.99"), NOW)
        service.stock_add(self.db, self.user_id, med["id"], dict(kind="adjustment", amount=250), NOW)
        self.assertEqual(self.db.execute("SELECT stock FROM medications").fetchone()[0], 250000)
        self.assertEqual(self.db.execute("SELECT sum(amount) FROM stock_movements").fetchone()[0], 250000)
        self.assertEqual(self.db.execute("SELECT price_cents FROM stock_movements WHERE kind='purchase'").fetchone()[0], 899)
        with self.assertRaises(domain.Invalid):
            service.stock_add(self.db, self.user_id, med["id"], dict(kind="adjustment", amount=-1), NOW)

    def test_isolation_covers_medications_history_stock_and_prescriptions(self):
        med = self.med()
        for operation in [lambda: service.history(self.db, self.other_id, med["id"]),
                          lambda: service.stock_add(self.db, self.other_id, med["id"], dict(amount=2), NOW),
                          lambda: service.record_dose(self.db, self.other_id, med["id"], dict(scheduled_at=NOW), NOW)]:
            with self.assertRaises(service.NotFound):
                operation()
        self.assertEqual(service.medications(self.db, self.other_id, NOW), [])
        rx = service.insert(self.db, "prescriptions", dict(title="Privada", user_id=self.other_id))
        with self.assertRaises(service.NotFound):
            self.med(prescription_id=rx)

    def test_unit_changes_cannot_reinterpret_existing_stock(self):
        med = self.med()
        data = dict(domain.serialize_med(med, NOW), start_at="2026-10-11T08:00:00Z", unit="ml")
        with self.assertRaises(domain.Invalid):
            service.medication_save(self.db, self.user, data, med["id"], NOW)

    def test_future_or_off_schedule_doses_are_rejected(self):
        med = self.med()
        for at in (NOW + 8 * 3600, NOW - 10, NOW + 15):
            with self.assertRaises(domain.Invalid):
                service.record_dose(self.db, self.user_id, med["id"], dict(scheduled_at=at), NOW)

    def test_manual_doses_require_active_treatment(self):
        med = self.med(schedule="as_needed")
        service.record_dose(self.db, self.user_id, med["id"], {}, NOW)
        self.db.execute("UPDATE medications SET active=0 WHERE id=?", (med["id"],))
        with self.assertRaises(domain.Invalid):
            service.record_dose(self.db, self.user_id, med["id"], {}, NOW + 1)

    def test_persistence_and_consistent_sqlite_backup(self):
        self.med()
        self.db.commit()
        with connect(self.path) as reloaded:
            self.assertEqual(reloaded.execute("SELECT stock FROM medications").fetchone()[0], 10500)
        with connect(self.folder.name + "/backup.sqlite") as backup:
            self.db.backup(backup)
            self.assertEqual(backup.execute("SELECT stock FROM medications").fetchone()[0], 10500)

    def test_export_only_contains_own_data_without_credentials(self):
        self.med()
        export = service.export_data(self.db, self.user)
        self.assertEqual(export["quantity_scale"], 1000)
        self.assertEqual(len(export["medications"]), 1)
        self.assertNotIn("password", json.dumps(export))
        other = self.db.execute("SELECT * FROM users WHERE id=?", (self.other_id,)).fetchone()
        self.assertEqual(service.export_data(self.db, other)["medications"], [])


class ScheduleTests(DatabaseTests):
    def test_interval_six_eight_twelve_and_twentyfour_hours(self):
        for hours in (6, 8, 12, 24):
            med = self.med(interval_hours=hours)
            self.assertEqual(domain.occurrences(med, NOW, NOW+48*3600), list(range(NOW, NOW+48*3600+1, hours*3600)))

    def test_forecast_uses_future_uncovered_dose_and_finite_end(self):
        med = self.med(dose=1, stock=2, interval_hours=8)
        forecast = domain.forecast(med, NOW)
        self.assertEqual(forecast["runs_out_at"], NOW + 16*3600)
        self.assertEqual(forecast["doses_left"], 2)
        self.assertTrue(forecast["stock_warning"])
        ended = dict(med, end_at=NOW+8*3600)
        self.assertTrue(domain.forecast(ended, NOW)["enough_until_end"])
        self.assertIsNone(domain.forecast(ended, NOW)["runs_out_at"])

    def test_taken_current_slot_is_not_counted_twice(self):
        med = self.med(dose=1, stock=2)
        service.record_dose(self.db, self.user_id, med["id"], dict(scheduled_at=NOW), NOW)
        snapshot = service.medications(self.db, self.user_id, NOW)[0]
        self.assertEqual(snapshot["stock"], 1)
        self.assertEqual(snapshot["runs_out_at"], NOW+16*3600)

    def test_pause_keeps_history_and_removes_upcoming_slots(self):
        med = self.med()
        service.record_dose(self.db, self.user_id, med["id"], dict(scheduled_at=NOW), NOW)
        self.db.execute("UPDATE medications SET active=0 WHERE id=?", (med["id"],))
        items = service.agenda(self.db, self.user, "2026-10-11", NOW)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "taken")

    def test_daily_times_follow_timezone_and_dst(self):
        med = self.med(schedule="daily", times=["08:00"], start_at="2026-03-28T00:00:00Z")
        after=domain.timestamp("2026-03-28T00:00:00Z")
        before=domain.timestamp("2026-03-30T23:59:59Z")
        slots=domain.occurrences(med, after, before)
        self.assertEqual(slots, [domain.timestamp(f"2026-03-{day}T{hour}:00:00Z") for day,hour in [(28,'07'),(29,'06'),(30,'06')]])
        self.assertEqual(slots[1]-slots[0],23*3600)

    def test_spring_gap_and_autumn_fold_do_not_duplicate_doses(self):
        spring = self.med(schedule="daily", times=["02:30", "03:30"], start_at="2026-03-28T00:00:00Z", dose=1, stock=3)
        start=domain.timestamp("2026-03-28T00:00:00Z")
        end=domain.timestamp("2026-03-30T23:59:59Z")
        slots=domain.occurrences(spring,start,end)
        self.assertEqual(len(slots),5)
        self.assertEqual(domain.forecast(spring,start)["runs_out_at"],slots[3])
        fall = self.med(schedule="daily", times=["02:30"], start_at="2026-10-25T00:00:00Z")
        slots=domain.occurrences(fall,domain.timestamp("2026-10-25T00:00:00Z"),domain.timestamp("2026-10-25T23:59:59Z"))
        self.assertEqual(slots,[domain.timestamp("2026-10-25T00:30:00Z")])

    def test_local_dates_are_interpreted_in_medication_timezone(self):
        data=dict(name="Jarabe", timezone="Europe/Madrid", start_local="2026-10-11T10:00", end_local="", dose=5,unit="ml",form="Jarabe")
        self.assertEqual(domain.medication_input(data,"Etc/UTC")["start_at"], NOW)
        data["start_local"]="2026-03-29T02:30"
        with self.assertRaises(domain.Invalid):
            domain.medication_input(data,"Etc/UTC")

    def test_no_date_projection_for_as_needed_or_paused(self):
        for overrides in [dict(schedule="as_needed"),dict(active=False)]:
            forecast=domain.forecast(self.med(**overrides),NOW)
            self.assertIsNone(forecast["runs_out_at"])
            self.assertFalse(forecast["stock_warning"])

    def test_bad_quantities_times_and_zones_rejected(self):
        for value in ["NaN", "Infinity", True, "0.0001", "foo"]:
            with self.assertRaises(domain.Invalid):
                domain.quantity(value)
        for overrides in [dict(dose=0),dict(stock=-1),dict(timezone="Invalid/Zone"),dict(interval_hours=float('nan')),dict(schedule="daily",times=["25:00"]),dict(schedule="daily",times=[])]:
            with self.assertRaises(domain.Invalid):
                self.med(**overrides)


class AlertTests(DatabaseTests):
    def test_generation_deduplicates_and_does_not_send_old_doses(self):
        self.med(dose=1,stock=1)
        alerts.generate(self.db,NOW)
        alerts.generate(self.db,NOW+30)
        kinds=[r[0] for r in self.db.execute("SELECT kind FROM alerts")]
        self.assertEqual(kinds.count('dose'),1)
        self.assertEqual(kinds.count('stock'),1)
        old=service.insert(self.db,"medications",dict(domain.medication_input(dict(name="Antiguo",start_at="2026-10-10T01:00:00Z",interval_hours=24),"Europe/Madrid"),user_id=self.user_id,stock=10000,created_at=NOW))
        alerts.generate(self.db,NOW)
        self.assertFalse(self.db.execute("SELECT 1 FROM alerts WHERE dedupe_key LIKE ?",(f"dose:{old}:%",)).fetchone())

    def test_taken_disabled_and_finished_medications_do_not_remind(self):
        med=self.med(stock=0,end_at="2026-10-11T08:00:00Z")
        service.record_dose(self.db,self.user_id,med["id"],dict(scheduled_at=NOW,status="skipped"),NOW)
        alerts.generate(self.db,NOW+30)
        self.assertEqual(self.db.execute("SELECT count(*) FROM alerts").fetchone()[0],0)

    def test_prescription_renewal_and_daily_stock_alerts(self):
        self.med(stock=0)
        service.insert(self.db,"prescriptions",dict(title="Receta",user_id=self.user_id,renewal_date="2026-10-17"))
        alerts.generate(self.db,NOW)
        alerts.generate(self.db,NOW+100)
        self.assertEqual(self.db.execute("SELECT count(*) FROM alerts WHERE kind='prescription'").fetchone()[0],1)
        alerts.generate(self.db,NOW+86400)
        self.assertEqual(self.db.execute("SELECT count(*) FROM alerts WHERE kind='stock'").fetchone()[0],2)

    def test_ntfy_is_opt_in_and_delivery_failures_do_not_affect_stock(self):
        med=self.med(stock=0)
        alerts.generate(self.db,NOW)
        calls=[]
        def sender(request,timeout):
            calls.append(request)
            class Response:
                status=200
                def __enter__(self):return self
                def __exit__(self,*args):pass
            return Response()
        alerts.deliver(self.db,NOW,sender)
        self.assertEqual(calls,[])
        self.db.execute("UPDATE users SET ntfy_enabled=1 WHERE id=?",(self.user_id,))
        self.db.commit()
        alerts.deliver(self.db,NOW,sender)
        self.assertEqual(len(calls),2)
        self.assertEqual(json.loads(calls[0].data)["topic"],self.user['ntfy_topic'])
        alerts.deliver(self.db,NOW+60,sender)
        self.assertEqual(len(calls),2)
        self.assertEqual(service.owned(self.db,'medications',med['id'],self.user_id)['stock'],0)


class AuthenticationAndApiTests(DatabaseTests):
    def request(self,path,method="GET",data=None,token=None,origin="http://localhost:8000",host="localhost:8000",fetch_site="same-origin"):
        handler=Handler.__new__(Handler)
        handler.command=method
        handler.client_address=("127.0.0.1",1234)
        handler.headers=Message()
        handler.headers['Host']=host
        handler.headers['Origin']=origin
        handler.headers['Sec-Fetch-Site']=fetch_site
        if token:handler.headers['Cookie']=f"pastillas_session={token}"
        encoded=json.dumps(data or {}).encode()
        handler.headers['Content-Type']='application/json'
        handler.headers['Content-Length']=str(len(encoded))
        handler.rfile=io.BytesIO(encoded)
        responses=[]
        handler.send=lambda status,body,content_type=None,headers=None:responses.append((status,body,headers))
        handler.api(self.db,path,{})
        return responses[0]

    def token(self,user_id=None):
        value=auth.session(self.db,user_id or self.user_id)
        self.db.commit()
        return value

    def test_password_hash_and_session_expiry(self):
        hashed=self.user['password']
        self.assertNotIn('contrasena',hashed)
        self.assertTrue(auth.verify_password('contrasena-larga-123',hashed))
        self.assertFalse(auth.verify_password('incorrecta',hashed))
        token=self.token()
        self.assertEqual(auth.current_user(self.db,token)['id'],self.user_id)
        self.db.execute('UPDATE sessions SET expires=0')
        self.assertIsNone(auth.current_user(self.db,token))

    def test_api_requires_login_and_rejects_cross_site_posts(self):
        with self.assertRaises(Unauthorized):self.request('/api/dashboard')
        with self.assertRaises(Forbidden):self.request('/api/medications','POST',{},self.token(),origin='https://otro-sitio.example',fetch_site='cross-site')

    def test_any_public_domain_ip_and_proxy_host_work_without_configuration(self):
        token=self.token()
        body=dict(timezone='Europe/Madrid',ntfy_topic=self.user['ntfy_topic'],ntfy_enabled=False,stock_alerts=True,prescription_alerts=True)
        # Una variable antigua tampoco vuelve a imponer restricciones a una instalación actualizada.
        with patch.dict(os.environ, {'PUBLIC_URL':'https://antiguo.example'}):
            for origin,host in [('https://pastillas.example','pastillas.example'),
                                ('http://192.168.1.25:8092','192.168.1.25:8092'),
                                ('https://otro-dominio.example','127.0.0.1:8000')]:
                response=self.request('/api/settings','PUT',body,token,origin=origin,host=host)
                self.assertEqual(response[0],200)

    def test_only_admin_can_create_users(self):
        token=self.token(self.other_id)
        with self.assertRaises(Forbidden):
            self.request('/api/users','POST',dict(username='cla',password='contrasena-nueva-123'),token)
        self.db.rollback()
        response=self.request('/api/users','POST',dict(username='cla',password='contrasena-nueva-123'),self.token())
        self.assertEqual(response[0],201)

    def test_login_cookie_password_change_and_logout(self):
        response=self.request('/api/login','POST',dict(username='ana',password='contrasena-larga-123'))
        self.assertEqual(response[0],200)
        cookie=response[2]['Set-Cookie']
        self.assertIn('HttpOnly',cookie)
        self.assertIn('SameSite=Lax',cookie)
        token=cookie.split(';')[0].split('=')[1]
        response=self.request('/api/password','PUT',dict(current_password='contrasena-larga-123',password='nueva-contrasena-123'),token)
        self.assertIsNone(auth.current_user(self.db,token))
        newtoken=response[2]['Set-Cookie'].split(';')[0].split('=')[1]
        self.assertIsNotNone(auth.current_user(self.db,newtoken))
        self.request('/api/logout','POST',{},newtoken)
        self.assertIsNone(auth.current_user(self.db,newtoken))

    def test_initial_setup_cannot_be_repeated(self):
        with self.assertRaises(service.Conflict):
            self.request('/api/setup','POST',dict(username='cla',password='contrasena-nueva-123'))


if __name__ == '__main__':
    unittest.main()
