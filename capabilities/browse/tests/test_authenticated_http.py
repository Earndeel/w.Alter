"""Authenticated session acceptance against a real, isolated HTTP fixture."""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'runtime')]
from browse_session import SessionManager, cookies_for_domain
from universal_extractor import ExtractionSpec
from universal_router import UniversalRouter

SECRET = 'synthetic-fixture-session-value'


@contextmanager
def site():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            authenticated = self.headers.get('Cookie') == 'session=' + SECRET
            requests.append({'path':self.path, 'authenticated':authenticated})
            if self.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', f'http://localhost:{self.server.server_port}/private')
                self.end_headers()
                return
            body = (json.dumps({'items':[{'content':'AUTHENTICATED_FIXTURE_OK'}]}) if authenticated else '<html>' + 'Please sign in. '*25 + '</html>').encode()
            self.send_response(200 if authenticated else 401)
            self.send_header('Content-Type', 'application/json' if authenticated else 'text/html')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', requests
    finally:
        server.shutdown();server.server_close();thread.join(2)


def session(tmp_path, monkeypatch, *, cookie=None):
    monkeypatch.setenv('WALTER_BROWSE_STATE_DIR',str(tmp_path))
    manager=SessionManager()
    sess=manager.create(session_id='fixture-only',identity='temporary',persistent=True)
    sess.authenticated=True;sess.cookie_count=1
    manager.save(sess,storage_state={'cookies':[cookie or {'name':'session','value':SECRET,'domain':'127.0.0.1','path':'/','httpOnly':True,'secure':False,'expires':-1}]})
    return manager, sess


def extract(url, sess):
    profile=Mock()
    router=UniversalRouter(profile_index=profile)
    spec=ExtractionSpec(expected_fields={'content':['content']},required_fields=['content'])
    result=asyncio.run(router.extract_one(url,spec,session=sess))
    # Authenticated content must not enter anonymous route/capability caches.
    profile.lookup.assert_not_called();profile.observe.assert_not_called();profile.observe_domain.assert_not_called()
    return result


def test_managed_session_real_authenticated_http_and_private_storage(tmp_path,monkeypatch):
    manager,sess=session(tmp_path,monkeypatch)
    assert manager.storage_state_path(sess).stat().st_mode & 0o777 == 0o600
    assert manager.storage_state_path(sess).parent.stat().st_mode & 0o777 == 0o700
    with site() as (url,requests):
        result=extract(url+'/private',sess)
    assert result.route=='probe-http' and result.result.records, result.summary()
    assert requests==[{'path':'/private','authenticated':True}]
    assert SECRET not in json.dumps(result.summary())
    manager.destroy(sess.id)
    assert not manager.storage_state_path(sess).exists()


def test_cross_origin_redirect_does_not_forward_credential_or_fallback(tmp_path,monkeypatch):
    _,sess=session(tmp_path,monkeypatch)
    with site() as (url,requests):
        result=extract(url+'/redirect',sess)
    assert result.route=='session-http' and not result.result.records
    assert requests==[{'path':'/redirect','authenticated':True}]
    assert SECRET not in json.dumps(result.summary())


@pytest.mark.parametrize('cookie',[
    {'name':'session','value':SECRET,'domain':'127.0.0.1','path':'/other','secure':False},
    {'name':'session','value':SECRET,'domain':'127.0.0.1','path':'/','secure':True},
    {'name':'session','value':SECRET,'domain':'127.0.0.1','path':'/','expires':1},
])
def test_cookie_scope_and_expiry_cannot_turn_login_page_into_success(tmp_path,monkeypatch,cookie):
    _,sess=session(tmp_path,monkeypatch,cookie=cookie)
    with site() as (url,requests):
        result=extract(url+'/private',sess)
    assert not result.result.records and result.route=='session-http'
    assert not any(item['authenticated'] for item in requests)


def test_child_cookie_never_sent_to_parent_or_unrelated_host():
    cookies=[{'name':'session','value':SECRET,'domain':'child.example.com','path':'/'},
             {'name':'wide','value':SECRET,'domain':'.example.com','path':'/'}]
    assert [item['name'] for item in cookies_for_domain(cookies,'example.com')]==['wide']
    assert [item['name'] for item in cookies_for_domain(cookies,'sub.child.example.com')]==['wide']
    assert not cookies_for_domain(cookies,'example.com.attacker.test')


def test_unreadable_session_and_proxy_mode_fail_closed(tmp_path,monkeypatch):
    manager,sess=session(tmp_path,monkeypatch)
    manager.storage_state_path(sess).chmod(0o644)
    with site() as (url,requests):
        result=extract(url+'/private',sess)
    assert not requests and not result.result.records
    manager.storage_state_path(sess).chmod(0o600)
    sess.network='proxy'
    with site() as (url,requests):
        result=extract(url+'/private',sess)
    assert not requests and not result.result.records
