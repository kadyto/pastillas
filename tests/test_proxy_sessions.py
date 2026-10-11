import io
import hashlib
import os
import tempfile
import unittest
from email.message import Message
from unittest.mock import patch

from app import auth, service
from app.db import connect, initialize
from app.server import Handler, Unauthorized


class ProxySessionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        path = self.folder.name + '/pastillas.sqlite'
        initialize(path)
        self.db = connect(path)
        self.user_id = service.create_user(self.db, dict(username='proxy-test', password='contrasena-proxy-123'))
        self.token = auth.session(self.db, self.user_id)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def handler(self, cookies=(), proto='https'):
        handler = Handler.__new__(Handler)
        handler.headers = Message()
        handler.headers['Host'] = 'backend-interno:8000'
        handler.headers['X-Forwarded-Proto'] = proto
        handler.headers['Origin'] = 'https://pastillas.example'
        handler.headers['Content-Type'] = 'application/json'
        handler.headers['Content-Length'] = '2'
        handler.headers['Sec-Fetch-Site'] = 'same-origin'
        for value in cookies:
            handler.headers.add_header('Cookie', value)
        handler.rfile = io.BytesIO(b'{}')
        handler.client_address = ('127.0.0.1', 1234)
        handler.command = 'POST'
        return handler

    def test_other_app_json_cookie_cannot_discard_our_session(self):
        cookie = f'preferencias={{"theme":"dark"}}; pastillas_session={self.token}'
        self.assertEqual(self.handler([cookie]).user(self.db)['id'], self.user_id)

    def test_other_app_loose_value_and_multiple_cookie_headers(self):
        handler = self.handler(['otra_app=texto con espacios', f'pastillas_session={self.token}; analitica=123'])
        self.assertEqual(handler.user(self.db)['id'], self.user_id)

    def test_expired_shadow_cookie_does_not_hide_a_valid_session(self):
        expired = auth.session(self.db, self.user_id)
        self.db.execute('UPDATE sessions SET expires=0 WHERE token=?', (hashlib.sha256(expired.encode()).hexdigest(),))
        self.db.commit()
        handler = self.handler([f'pastillas_session={expired}; pastillas_session="{self.token}"'])
        self.assertEqual(handler.user(self.db)['id'], self.user_id)

    def test_foreign_cookie_and_invalid_session_do_not_authenticate(self):
        for cookie in [f'otra_session={self.token}', 'pastillas_session=incorrecta', 'pastillas_session=' + 'a' * 43]:
            with self.assertRaises(Unauthorized):
                self.handler([cookie]).user(self.db)

    def test_https_proxy_sets_secure_http_only_lax_cookie_automatically(self):
        with patch.dict(os.environ, {'COOKIE_SECURE': 'auto'}):
            value = self.handler().cookie(self.token)['Set-Cookie']
            self.assertIn('; Secure', value)
            self.assertIn('; HttpOnly', value)
            self.assertIn('; SameSite=Lax', value)
            self.assertNotIn('Domain=', value)
            self.assertNotIn('; Secure', self.handler(proto='http').cookie(self.token)['Set-Cookie'])

    def test_explicit_secure_cookie_configuration_is_preserved(self):
        with patch.dict(os.environ, {'COOKIE_SECURE': 'true'}):
            self.assertIn('; Secure', self.handler(proto='http').cookie(self.token)['Set-Cookie'])
        with patch.dict(os.environ, {'COOKIE_SECURE': 'false'}):
            self.assertNotIn('; Secure', self.handler().cookie(self.token)['Set-Cookie'])

    def test_logout_revokes_sessions_even_with_other_app_cookies(self):
        second_token = auth.session(self.db, self.user_id)
        self.db.commit()
        handler = self.handler([f'otra_app={{"foo":"bar"}}; pastillas_session={self.token}; pastillas_session={second_token}'])
        responses = []
        handler.send = lambda status, body, content_type=None, headers=None: responses.append((status, body, headers))
        handler.api(self.db, '/api/logout', {})
        self.assertEqual(responses[0][0], 200)
        self.assertIsNone(auth.current_user(self.db, self.token))
        self.assertIsNone(auth.current_user(self.db, second_token))
        self.assertIn('Max-Age=0', responses[0][2]['Set-Cookie'])


if __name__ == '__main__':
    unittest.main()
