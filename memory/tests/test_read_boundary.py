from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys

from walter_memory import read_policy, search


class Connection:
    """Batched canonical owners keyed by event id (the read boundary looks events up via core.event_keys)."""
    def __init__(self, rows):
        self.rows = rows
    def execute(self, sql, args=()):
        self.sql, self.args = sql, args; return self
    def fetchall(self):
        if 'event_keys' in self.sql:
            return [{'event_id': i, 'occurred_at': None} for i in self.args[0] if i in self.rows]
        if 'event.retracted' in self.sql:
            return []
        if 'core.events' in self.sql:
            return [{'id': i, **self.rows[i]} for i in self.args[1]]
        return []


def test_filter_enforces_current_owner_and_freshness(monkeypatch):
    monkeypatch.setattr(read_policy, '_retracted', (float('inf'), frozenset({'retracted'})))
    conn = Connection({'public': {'privacy_class': 'cloud_allowed', 'content': 'public decision'},
                       'private': {'privacy_class': 'local_only', 'content': 'private decision'},
                       'stale': {'privacy_class': 'cloud_allowed', 'content': 'new decision'},
                       'retracted': {'privacy_class': 'cloud_allowed', 'content': 'public decision'}})
    rows = [dict(kind='event', ref_id=key, text=text, privacy_class='cloud_allowed')
            for key, text in [('public','public decision'),('private','private decision'),('stale','old decision'),
                              ('retracted','public decision'),('missing','public decision')]]
    assert [r['ref_id'] for r in read_policy.filter_cloud_rows(conn, rows)] == ['public']


def test_noise_rules_hide_runtime_artefacts_not_messages():
    noise = ['[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted',
             '[Your active task list was preserved across context compression]',
             'The following is the Codex agent history added since your last review',
             '[12] user: please continue the migration',
             '{"i":0,"result":{"result":"## Mémoire pertinente\\n- a fact"}}',
             'Mémoire W.Alter (injectée automatiquement pour ce message) …', 'ok', 'vas y']
    assert all(search.noise_reason(t, 'hermes') for t in noise)
    assert search.noise_reason('{"risk_level":"low","user_authorization":"high"}', 'codex') == 'tool_output'
    for t in ['Monsieur préfère recevoir les liens sur Telegram.', 'On se voit demain à 18h au bureau ?']:
        assert search.noise_reason(t, 'hermes') is None and search.noise_reason(t, 'beeper') is None


def test_dedupe_keeps_best_ranked_of_repeated_facts(monkeypatch):
    import numpy as np
    monkeypatch.setattr(search, 'embed', lambda texts: np.array([[1.0, 0.0] if 'Brave' in t else [0.0, 1.0] for t in texts]))
    rows = [{'text': 'Monsieur utilise Brave.'}, {'text': 'monsieur utilise brave'}, {'text': 'Monsieur utilise Brave sur Mac.'},
            {'text': 'Fuseau UTC+7.'}]
    assert [r['text'] for r in search.dedupe(rows)] == ['Monsieur utilise Brave.', 'Fuseau UTC+7.']


def test_rerank_private_query_never_calls_network(monkeypatch):
    monkeypatch.setattr(read_policy, 'query_privacy', lambda *args: 'local_only')
    monkeypatch.setattr(search.httpx, 'post', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('network')))
    rows = [{'text': 'fixture', 'privacy_class': 'cloud_allowed'}]
    assert search._rerank('private fixture', rows, 5) == rows


def test_rerank_stale_private_projection_never_calls_network(monkeypatch):
    monkeypatch.setattr(read_policy, 'query_privacy', lambda *args: 'cloud_allowed')
    @contextmanager
    def connect():
        yield Connection({'private': {'privacy_class': 'local_only', 'content': 'fixture'}})
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
