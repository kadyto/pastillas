import hashlib
import hmac
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from app import domain, service, updates
from app.db import connect, initialize
from test_pastillas import NOW

SHA = 'a' * 40
WEBHOOK = {'DOCKHAND_WEBHOOK_URL': 'https://dockhand.example/api/git/stacks/42/webhook',
           'DOCKHAND_WEBHOOK_SECRET': 'secreto-solo-de-pruebas'}


class Response(io.BytesIO):
    status = 200


def provider(latest='0.4.1', calls=None):
    def open_request(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        if request.full_url == updates.REF_URL:
            return Response(json.dumps({'object': {'sha': SHA}}).encode())
        assert request.full_url == f'https://raw.githubusercontent.com/kadyto/pastillas/{SHA}/app/__init__.py'
        return Response(f'__version__ = "{latest}"\n'.encode())
    return open_request


class VersionTests(unittest.TestCase):
    def setUp(self):
        installed=patch('app.updates.__version__','0.4.0')
        installed.start();self.addCleanup(installed.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name) / 'app.sqlite')
        initialize(self.path)

    def tearDown(self):
        self.folder.cleanup()

    def status(self):
        with connect(self.path) as db:
            return updates.status(db, NOW)

    def test_daily_cache_survives_restart_and_manual_check_bypasses_it(self):
        calls = []
        opener = provider(calls=calls)
        result = updates.check(now=NOW, path=self.path, opener=opener)
        self.assertTrue(result['update_available'])
        self.assertEqual(result['state'], 'available')
        initialize(self.path)
        updates.check(now=NOW + 86399, path=self.path, opener=opener)
        self.assertEqual(len(calls), 2)
        updates.check(force=True, now=NOW + 86399, path=self.path, opener=opener)
        self.assertEqual(len(calls), 4)
        updates.check(now=NOW + 86400, path=self.path, opener=opener)
        self.assertEqual(len(calls), 4)
        updates.check(now=NOW + 86399 + 86400, path=self.path, opener=opener)
        self.assertEqual(len(calls), 6)
        self.assertFalse(self.status()['checking'])

    def test_numeric_comparison_and_unknown_failure_are_not_reported_as_current(self):
        self.assertGreater(updates.version('0.10.0'), updates.version('0.9.9'))
        self.assertEqual(self.status()['state'], 'unchecked')
        with patch('app.updates.__version__', '0.9.9'):
            result = updates.check(now=NOW, path=self.path, opener=provider('0.10.0'))
        self.assertTrue(result['update_available'])
        def failing(request, timeout):
            raise OSError('private URL and secret must not be exposed')
        result = updates.check(force=True, now=NOW + 1, path=self.path, opener=failing)
        self.assertEqual(result['state'], 'unavailable')
        self.assertEqual(result['latest_version'], '0.10.0')
        self.assertEqual(result['checked_at'], NOW)
        self.assertNotIn('private URL', result['error'])
        calls = []
        updates.check(now=NOW + 2, path=self.path, opener=provider(calls=calls))
        self.assertEqual(calls, [])
        result = updates.check(force=True, now=NOW + 3, path=self.path, opener=provider(updates.__version__))
        self.assertEqual(result['state'], 'current')
        self.assertFalse(result['error'])

    def test_invalid_remote_versions_never_replace_the_last_valid_result(self):
        updates.check(now=NOW, path=self.path, opener=provider())
        for value in ('not-a-version', '1.2', '1.2.3.4', '1.2.3;bad'):
            with self.subTest(value=value):
                result = updates.check(force=True, now=NOW + 1, path=self.path, opener=provider(value))
                self.assertEqual(result['state'], 'unavailable')
                self.assertEqual(result['latest_version'], '0.4.1')

    def test_concurrent_checks_do_not_duplicate_network_calls_or_hold_sqlite_lock(self):
        started, release = threading.Event(), threading.Event()
        calls = []
        def slow(request, timeout):
            if request.full_url == updates.REF_URL:
                started.set()
                self.assertTrue(release.wait(5))
            return provider(calls=calls)(request, timeout)
        thread = threading.Thread(target=updates.check, kwargs={'now': NOW, 'path': self.path, 'opener': slow})
        thread.start()
        self.assertTrue(started.wait(5))
        try:
            busy = updates.check(force=True, now=NOW, path=self.path, opener=provider(calls=calls))
            self.assertTrue(busy['checking'])
            with connect(self.path) as db:
                db.execute('UPDATE app_updates SET deploy_target=? WHERE id=1', ('0.4.1',))
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(calls), 2)

    def test_webhook_is_signed_queued_and_credentials_are_not_in_status(self):
        updates.check(now=NOW, path=self.path, opener=provider())
        tasks = []
        with patch.dict(os.environ, WEBHOOK):
            result = updates.request_deploy(now=NOW + 1, path=self.path, launch=tasks.append)
            self.assertEqual(result['deploy_status'], 'queued')
            self.assertNotIn(WEBHOOK['DOCKHAND_WEBHOOK_SECRET'], json.dumps(result))
            self.assertNotIn(WEBHOOK['DOCKHAND_WEBHOOK_URL'], json.dumps(result))
            with self.assertRaises(domain.Invalid):
                updates.request_deploy(now=NOW + 2, path=self.path, launch=tasks.append)
        requests = []
        def webhook(request, timeout):
            requests.append(request)
            self.assertEqual(timeout, 90)
            return Response(b'{"success":true}')
        updates.deploy('0.4.1', SHA, (WEBHOOK['DOCKHAND_WEBHOOK_URL'], WEBHOOK['DOCKHAND_WEBHOOK_SECRET']), path=self.path, opener=webhook)
        request = requests[0]
        signature = 'sha256=' + hmac.new(WEBHOOK['DOCKHAND_WEBHOOK_SECRET'].encode(), request.data, hashlib.sha256).hexdigest()
        self.assertEqual(request.get_header('X-hub-signature-256'), signature)
        self.assertEqual(json.loads(request.data)['ref'], 'refs/heads/main')
        self.assertEqual(self.status()['deploy_status'], 'requested')
        with patch('app.updates.__version__', '0.4.1'):
            updates.recover(self.path)
            self.assertEqual(self.status()['deploy_status'], 'completed')
        self.assertEqual(len(tasks), 1)

    def test_webhook_failure_timeout_and_skipped_are_explicit_and_never_retried(self):
        settings = (WEBHOOK['DOCKHAND_WEBHOOK_URL'], WEBHOOK['DOCKHAND_WEBHOOK_SECRET'])
        cases = [('failed', Response(b'{"success":false}')),
                 ('skipped', Response(b'{"success":true,"skipped":true}')),
                 ('failed', urllib.error.HTTPError(settings[0], 401, 'secret', {}, None)),
                 ('unknown', TimeoutError('private connection details'))]
        for expected, response in cases:
            requests = []
            def webhook(request, timeout):
                requests.append(request)
                if isinstance(response, Exception):
                    raise response
                return response
            updates.deploy('0.4.1', SHA, settings, path=self.path, opener=webhook)
            result = self.status()
            self.assertEqual(result['deploy_status'], expected)
            self.assertTrue(result['deploy_error'])
            self.assertNotIn('private connection', result['deploy_error'])
            self.assertEqual(len(requests), 1)

    def test_unconfigured_or_invalid_webhook_and_current_version_cannot_deploy(self):
        with patch.dict(os.environ, {'DOCKHAND_WEBHOOK_URL': '', 'DOCKHAND_WEBHOOK_SECRET': ''}):
            with self.assertRaises(domain.Invalid):
                updates.request_deploy(path=self.path)
        for url in ('file:///etc/passwd', 'https://dockhand.example/other', 'https://dockhand.example/api/git/stacks/1/webhook?secret=private'):
            with patch.dict(os.environ, dict(WEBHOOK, DOCKHAND_WEBHOOK_URL=url)):
                self.assertFalse(self.status()['deployment_configured'])
                with self.assertRaises(domain.Invalid):
                    updates.request_deploy(path=self.path)
        updates.check(now=NOW, path=self.path, opener=provider(updates.__version__))
        with patch.dict(os.environ, WEBHOOK), self.assertRaisesRegex(domain.Invalid, 'última versión'):
            updates.request_deploy(now=NOW + 1, path=self.path)

    def test_schema_four_upgrade_keeps_expiry_stock_and_history(self):
        with connect(self.path) as db:
            uid = service.create_user(db, dict(username='ana', password='contrasena-larga-123'))
            user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            service.medication_save(db, user, dict(name='Paracetamol', schedule='as_needed', stock=20,
                expiry_date='2027-05-31', start_at='2026-10-11T08:00:00Z'), now=NOW)
            before = dict(db.execute('SELECT * FROM medications').fetchone())
            db.execute('DROP TABLE app_updates')
            db.execute('PRAGMA user_version=4')
        initialize(self.path)
        initialize(self.path)
        with connect(self.path) as db:
            self.assertEqual(dict(db.execute('SELECT * FROM medications').fetchone()), before)
            self.assertEqual(db.execute('SELECT count(*) FROM stock_movements').fetchone()[0], 1)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 6)
            self.assertEqual(updates.status(db)['state'], 'unchecked')
        with sqlite3.connect(self.path + '.pre-v5.sqlite') as backup:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 4)
            self.assertEqual(backup.execute('SELECT expiry_date FROM medications').fetchone()[0], '2027-05-31')


if __name__ == '__main__':
    unittest.main()
