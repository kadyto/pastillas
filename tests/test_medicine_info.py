import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app import medicine_info as info, service, auth
from app.db import connect, initialize
from app.domain import Invalid
from test_pastillas import DatabaseTests, NOW
from medicine_fixture import MEDICINE, NOTE, SUPPLY, fetch

URL = 'https://www.vademecum.es/espana/medicamento/27631/omacor-1000-mg-capsulas-blandas'


class InputTests(unittest.TestCase):
    def test_url_is_only_a_reference_never_a_fetch_target(self):
        self.assertEqual(info.vademecum_url(URL), URL)
        self.assertIn('/espana/equivalencias/27631/', info.equivalents_url(URL))
        for bad in ['http://www.vademecum.es/espana/medicamento/1/a', 'https://127.0.0.1/',
                    'https://www.vademecum.es@127.0.0.1/espana/medicamento/1/a', URL+'?redirect=http://localhost',
                    'https://www.vademecum.es:443/espana/medicamento/1/a', 'https://[invalid',
                    'https://www.vademecum.es/espana/medicamento/1/%2e%2e']:
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                info.vademecum_url(bad)

    def test_sanitizer_retains_tables_and_text_without_executable_attributes(self):
        result = info.sanitize_document('<p onclick="evil()">Dosis &amp; <strong>texto</strong></p><script>alert(1)</script>'
                                        '<iframe src="//evil"></iframe><a href="javascript:evil()">enlace</a>'
                                        '<table><tr><td colspan="2" style="color:red">dato</td></tr></table>'
                                        '<img src="//evil" onerror="evil()" alt="diagrama">')
        self.assertIn('<td colspan="2">dato</td>', result)
        self.assertIn('Dosis &amp;', result)
        self.assertIn('diagrama', result)
        for bad in ['onclick','script','iframe','javascript:','src=','onerror','style=','alert(1)']:
            self.assertNotIn(bad, result)


class InformationTests(DatabaseTests):
    def setUp(self):
        super().setUp()
        self.medication = self.med()
        self.db.execute('INSERT INTO medicine_links VALUES(?,?,?,?,?,?)',
                        (self.medication['id'],URL,'99999','999001',MEDICINE['nombre'],'Envase 28'))
        self.db.commit()

    def queue(self, now=NOW):
        info.enqueue_user(self.db,self.user_id,now)
        self.db.commit()

    def test_login_checks_at_most_once_per_twelve_hours_across_connections(self):
        self.queue()
        with patch.object(info,'fetch_json',side_effect=fetch) as source:
            self.assertTrue(info.process_one(self.path,NOW))
            count=source.call_count
            self.assertEqual(count,3)
            for when in [NOW+1,NOW+60,NOW+43199]:
                self.queue(when)
                self.assertFalse(info.process_one(self.path,when))
                service.dashboard(self.db,self.user,when)
            self.assertEqual(source.call_count,count)
            self.queue(NOW+43200)
            self.assertTrue(info.process_one(self.path,NOW+43200))
            self.assertEqual(source.call_count,6)
        self.assertEqual(self.db.execute("SELECT count(*) FROM alerts WHERE kind IN ('safety','supply')").fetchone()[0],2)
        self.assertEqual(info.information(self.db,self.medication['id'],NOW+43201)['status'],'fresh')

    def test_failed_attempt_keeps_previous_data_and_also_waits_twelve_hours(self):
        self.queue()
        with patch.object(info,'fetch_json',side_effect=fetch):
            info.process_one(self.path,NOW)
        self.queue(NOW+info.TTL)
        with patch.object(info,'fetch_json',side_effect=info.SourceUnavailable(info.ERROR)) as source:
            info.process_one(self.path,NOW+info.TTL)
            self.queue(NOW+info.TTL+1)
            self.assertFalse(info.process_one(self.path,NOW+info.TTL+1))
            self.assertEqual(source.call_count,1)
        result=info.information(self.db,self.medication['id'],NOW+info.TTL+1)
        self.assertEqual(result['status'],'unavailable')
        self.assertTrue(result['error'])
        self.assertEqual(len(result['data']['notices']),2)
        self.assertEqual(result['checked_at'],NOW)

    def test_same_public_cache_for_two_users_but_separate_private_alerts(self):
        other=self.db.execute('SELECT * FROM users WHERE id=?',(self.other_id,)).fetchone()
        second=service.medication_save(self.db,other,dict(name='Otro',form='Pastillas',unit='pastillas',dose=1,
                         stock=10,schedule='interval',interval_hours=24,start_at='2026-10-11T08:00:00Z'),now=NOW)
        self.db.execute('INSERT INTO medicine_links VALUES(?,?,?,?,?,?)',(second,'','99999','999001','Otro','28'))
        self.db.commit();self.queue()
        with patch.object(info,'fetch_json',side_effect=fetch) as source:
            info.process_one(self.path,NOW)
            info.enqueue_user(self.db,self.other_id,NOW+1);self.db.commit()
            self.assertFalse(info.process_one(self.path,NOW+1))
            self.assertEqual(source.call_count,3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM alerts WHERE user_id=?',(self.other_id,)).fetchone()[0],2)
        self.assertEqual(len(service.export_data(self.db,self.user)['medicine_links']),1)

    def test_shortages_are_specific_to_selected_pack_and_resolved_ones_are_excluded(self):
        item=dict(info.information(self.db,self.medication['id'])['link']);item['cn']='999002'
        with patch.object(info,'fetch_json',side_effect=fetch):
            result=info.load_information(item)
        self.assertEqual([n['kind'] for n in result['notices']],['safety'])
        item['cn']='999001'
        with patch.object(info,'fetch_json',side_effect=lambda e: [dict(SUPPLY,activo=False)] if e.startswith('psuministro/') else dict(MEDICINE,presentaciones=[dict(MEDICINE['presentaciones'][0],psum=False)]) if e.startswith('medicamento?') else fetch(e)):
            result=info.load_information(item)
        self.assertFalse(any(n['kind']=='supply' for n in result['notices']))

    def test_notes_use_publication_date_and_dedupe_survives_alert_pruning(self):
        self.queue()
        with patch.object(info,'fetch_json',side_effect=fetch):
            info.process_one(self.path,NOW)
        result=info.information(self.db,self.medication['id'],NOW)
        self.assertEqual(result['data']['notices'][0]['date'],NOTE['fecha']//1000)
        self.db.execute('DELETE FROM alerts');self.db.commit()
        self.queue(NOW+info.TTL)
        with patch.object(info,'fetch_json',side_effect=fetch):
            info.process_one(self.path,NOW+info.TTL)
        self.assertEqual(self.db.execute('SELECT count(*) FROM alerts').fetchone()[0],0)

    def test_background_check_does_not_hold_database_write_lock_during_network(self):
        self.queue()
        def provider(endpoint):
            with connect(self.path) as other:
                other.execute('UPDATE medications SET stock=stock+1 WHERE id=?',(self.medication['id'],))
            return fetch(endpoint)
        with patch.object(info,'fetch_json',side_effect=provider):
            self.assertTrue(info.process_one(self.path,NOW))
        self.assertEqual(self.db.execute('SELECT stock FROM medications').fetchone()[0],10503)

    def test_multiple_workers_claim_one_job(self):
        self.queue()
        with patch.object(info,'fetch_json',side_effect=fetch) as source:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:info.process_one(self.path,NOW),range(4)))
        self.assertEqual(results.count(True),1)
        self.assertEqual(source.call_count,3)

    def test_paused_medications_are_not_enqueued(self):
        self.db.execute('UPDATE medications SET active=0');self.db.commit();self.queue()
        with patch.object(info,'fetch_json') as source:
            self.assertFalse(info.process_one(self.path,NOW))
            source.assert_not_called()

    def test_crashed_job_can_retry_after_expiry(self):
        self.queue()
        self.db.execute('UPDATE medicine_cache SET pending=2,attempted_at=?,expires_at=?',(NOW,NOW+info.TTL));self.db.commit()
        self.queue(NOW+1)
        self.assertFalse(info.process_one(self.path,NOW+1))
        self.queue(NOW+info.TTL)
        with patch.object(info,'fetch_json',side_effect=fetch):
            self.assertTrue(info.process_one(self.path,NOW+info.TTL))

    def test_link_validates_owner_and_pack_without_overwriting_treatment(self):
        with patch.object(info,'fetch_json',side_effect=fetch), patch.object(info,'enqueue_user'):
            with self.assertRaises(service.NotFound):
                info.link(self.db,self.other_id,self.medication['id'],{},self.path)
            with self.assertRaises(Invalid):
                info.link(self.db,self.user_id,self.medication['id'],dict(nregistro='99999',cn='111111'),self.path)
            info.link(self.db,self.user_id,self.medication['id'],dict(nregistro='99999',cn='999002',vademecum_url=URL),self.path)
            self.db.commit()
        med=service.owned(self.db,'medications',self.medication['id'],self.user_id)
        self.assertEqual((med['name'],med['dose'],med['stock'],med['interval_hours']),('Mi medicamento',500,10500,8))

    def test_url_search_uses_name_not_vademecum_identifier(self):
        with patch.object(info,'fetch_json',side_effect=fetch) as source:
            result=info.search(URL,path=self.path)
        self.assertEqual(result['query'],'omacor')
        self.assertIn('nombre=omacor',source.call_args.args[0])
        self.assertNotIn('27631',source.call_args.args[0])
        self.assertEqual(result['vademecum_url'],URL)

    def test_documents_are_cached_and_sanitized(self):
        with patch.object(info,'fetch_json',side_effect=fetch) as source:
            first=info.document('99999','2',self.path)
            second=info.document('99999','2',self.path)
        self.assertEqual(first,second);self.assertEqual(source.call_count,1)
        self.assertIn('<table>',first['sections'][0]['html'])
        self.assertNotIn('script',first['sections'][0]['html'])


class MigrationTests(unittest.TestCase):
    def test_version_one_is_backed_up_migrated_and_preserved_on_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'db.sqlite');initialize(path)
            with connect(path) as db:
                uid=service.create_user(db,dict(username='ana',password='contrasena-larga-123'))
                user=db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                service.medication_save(db,user,dict(name='Conservado',form='Pastillas',unit='pastillas',dose=1,stock=40,schedule='as_needed',start_at='2026-10-11T08:00:00Z'),now=NOW)
                db.execute('DROP TABLE medicine_notice_seen');db.execute('DROP TABLE medicine_links');db.execute('DROP TABLE medicine_cache')
                db.execute('PRAGMA user_version=1')
            initialize(path);initialize(path)
            with connect(path) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
                self.assertEqual(db.execute('SELECT stock FROM medications').fetchone()[0],40000)
                self.assertTrue(auth.verify_password('contrasena-larga-123',db.execute('SELECT password FROM users').fetchone()[0]))
            with sqlite3.connect(path+'.pre-v2.sqlite') as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT name FROM medications').fetchone()[0],'Conservado')
