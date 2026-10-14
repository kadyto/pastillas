"""GitHub y Dockhand sintéticos para probar los controles sin despliegues reales."""
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import updates
from app import server

# Versiones sintéticas estables, independientes del lanzamiento probado.
updates.__version__ = server.__version__ = '0.4.0'

os.environ['DOCKHAND_WEBHOOK_URL'] = 'https://dockhand.example/api/git/stacks/42/webhook'
os.environ['DOCKHAND_WEBHOOK_SECRET'] = 'secreto-sintetico-del-navegador'
fixture = {'latest': '0.4.1', 'fail': False, 'github_requests': 0, 'deploy_requests': 0}


class Response(io.BytesIO):
    status = 200


def github(request, timeout):
    fixture['github_requests'] += 1
    if fixture['fail']:
        raise OSError('Fallo sintético')
    if request.full_url == updates.REF_URL:
        return Response(json.dumps({'object': {'sha': 'a' * 40}}).encode())
    return Response(f'__version__ = "{fixture["latest"]}"\n'.encode())


def webhook(request, timeout):
    fixture['deploy_requests'] += 1
    return Response(b'{"success":true}')


original_check, original_deploy = updates.check, updates.deploy


def check(force=False, now=None, path=None, opener=None):
    return original_check(force, now, path, github)


def deploy(target, sha, settings, path=None, opener=None):
    return original_deploy(target, sha, settings, path, webhook)


updates.check, updates.deploy = check, deploy


class Handler(server.Handler):
    def api(self, db, path, query):
        if path == '/api/test-updates':
            user = self.user(db)
            if self.command == 'POST':
                if not user['admin']:
                    raise server.Forbidden('Solo pruebas del administrador')
                body = self.body()
                for key in ('latest', 'fail'):
                    if key in body:
                        fixture[key] = body[key]
                if body.get('unconfigured'):
                    os.environ['DOCKHAND_WEBHOOK_URL'] = ''
                    os.environ['DOCKHAND_WEBHOOK_SECRET'] = ''
            return self.send(200, fixture)
        return super().api(db, path, query)


server.Handler = Handler
server.main()
