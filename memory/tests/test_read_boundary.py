from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys

from walter_memory import read_policy, search


class Connection:
    def __init__(self, rows):
        self.rows = rows
    def execute(self, sql, args):
        self.value = self.rows.get(args[0]); return self
    def fetchone(self):
        return self.value


def test_filter_enforces_current_owner_and_freshness():
    conn = Connection({'public': {'privacy_class': 'cloud_allowed', 'allowed': True, 'content': 'public decision'},
                       'private': {'privacy_class': 'local_only', 'allowed': True, 'content': 'private decision'},
                       'stale': {'privacy_class': 'cloud_allowed', 'allowed': True, 'content': 'new decision'}})
    rows = [dict(kind='event', ref_id=key, text=text, privacy_class='cloud_allowed')
            for key, text in [('public','public decision'),('private','private decision'),('stale','old decision')]]
    assert [r['ref_id'] for r in read_policy.filter_cloud_rows(conn, rows)] == ['public']


def test_rerank_private_query_never_calls_network(monkeypatch):
    monkeypatch.setattr(read_policy, 'query_privacy', lambda *args: 'local_only')
    monkeypatch.setattr(search.httpx, 'post', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('network')))
    rows = [{'text': 'fixture', 'privacy_class': 'cloud_allowed'}]
    assert search._rerank('private fixture', rows, 5) == rows


def test_rerank_stale_private_projection_never_calls_network(monkeypatch):
    monkeypatch.setattr(read_policy, 'query_privacy', lambda *args: 'cloud_allowed')
    @contextmanager
    def connect():
        yield Connection({'private': {'privacy_class': 'local_only', 'content': 'fixture', 'allowed': True}})
    monkeypatch.setattr(search, 'connection', connect)
    monkeypatch.setattr(search.httpx, 'post', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('network')))
    rows = [{'kind': 'event', 'ref_id':'private', 'text': 'fixture', 'privacy_class': 'cloud_allowed'}]
    assert search._rerank('fixture query', rows, 5) == rows


def test_http_port_uses_same_dispatch_and_never_echoes_error(monkeypatch):
    from fastapi.testclient import TestClient
    from walter_memory import gateway, agent_memory
    gateway.app.dependency_overrides[gateway.auth] = lambda: None
    try:
        seen=[]
        monkeypatch.setattr(agent_memory,'dispatch',lambda payload:seen.append(payload) or {'status':'ok'})
        client=TestClient(gateway.app)
        assert client.post('/v1/agent-memory',json={'method':'recall','args':{'query':'public fixture'}}).json()['status']=='ok'
        assert seen[0]['version']==1 and seen[0]['method']=='recall'
        def failing(payload):raise ValueError('secret fixture must not be echoed')
        monkeypatch.setattr(agent_memory,'dispatch',failing)
        response=client.post('/v1/agent-memory',json={'method':'recall','args':{'query':'public fixture'}})
        assert response.status_code==422 and 'secret' not in response.text
    finally:
        gateway.app.dependency_overrides.clear()


def test_client_imports_without_database_or_harness_dependencies(tmp_path):
    import subprocess
    root = str(Path(__file__).resolve().parents[1])
    code = "import sys;sys.path.insert(0,"+repr(root)+");from walter_memory import client;assert 'psycopg' not in sys.modules;assert 'agent' not in sys.modules"
    subprocess.run([sys.executable,'-S','-c',code],check=True,capture_output=True)


def test_transport_failure_redacts_response_and_never_retries_write(monkeypatch,tmp_path):
    from walter_memory import client
    env=tmp_path/'.env';env.write_text('WALTER_MEMORY_GATEWAY_TOKEN=fixture-only');env.chmod(0o600)
    monkeypatch.setattr(client,'ENV_FILE',env)
    calls=[]
    def failing(request,**kw):
        calls.append(request);raise RuntimeError('private provider response')
    monkeypatch.setattr(client.urllib.request,'urlopen',failing)
    response=client.call('retain',{'content':'test'},caller='test-port')
    assert len(calls)==1 and 'private provider response' not in json.dumps(response)
    assert response['status']=='error'
