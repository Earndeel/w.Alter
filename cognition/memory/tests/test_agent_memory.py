from contextlib import contextmanager
from pathlib import Path
import ast
import json

import pytest
from walter_memory import agent_memory as m


@pytest.fixture
def local(monkeypatch):
    class Conn:
        def execute(self,sql,args=()): return self
        def fetchone(self): return {'privacy_class':'cloud_allowed','content':'Public fixture decision','allowed':True}
    @contextmanager
    def connection(): yield Conn()
    monkeypatch.setattr(m,'connection',connection)
    monkeypatch.setattr(m.privacy,'classify',lambda *a,**kw:('cloud_allowed',[]))
    monkeypatch.setattr(m.privacy,'classify_event',lambda *a,**kw:'cloud_allowed')
    monkeypatch.setattr(m.llm,'chat',lambda *a,**kw:pytest.fail('external model must not be called'))
    return Conn()


def row(cls='cloud_allowed'):
    return {'kind':'event','ref_id':'11111111-1111-1111-1111-111111111111','privacy_class':cls,'text':'Public fixture decision','occurred_at':'2026-10-18'}


def test_recall_uses_local_search_and_cloud_canonical_scope(monkeypatch,local):
    seen=[]
    def search(query,**kw): seen.append(kw); return [row('local_only'),row()]
    monkeypatch.setattr(m.search,'search',search)
    out=m.recall('a project')
    assert out['status']=='ok' and len(out['records'])==1
    assert seen[0]['max_privacy']=='cloud_allowed' and seen[0]['rerank'] is False
    assert out['records'][0]['privacy_class']=='cloud_allowed'


def test_private_query_refuses_before_embedding_or_model(monkeypatch,local):
    monkeypatch.setattr(m.privacy,'classify',lambda *a,**kw:('local_only',[]))
    monkeypatch.setattr(m.search,'search',lambda *a,**kw:pytest.fail('query must not reach embeddings'))
    assert m.recall('private fixture')['status']=='refused_privacy'
    assert m.reflect('private fixture')['status']=='refused_privacy'


def test_stale_index_does_not_loosen_canonical_owner(monkeypatch,local):
    monkeypatch.setattr(local.__class__,'fetchone',lambda _: {'privacy_class':'local_only'})
    monkeypatch.setattr(m.search,'search',lambda *a,**kw:[row()])
    assert m.recall('a project')['records']==[]


def test_legacy_derived_without_provenance_is_excluded(monkeypatch,local):
    monkeypatch.setattr(local.__class__,'fetchone',lambda _: {'privacy_class':'cloud_allowed','status':'derived','source_count':0,'sources_allowed':True})
    value=row(); value['kind']='derived'
    monkeypatch.setattr(m.search,'search',lambda *a,**kw:[value])
    assert m.recall('a project')['records']==[]


def test_retain_classifies_note_and_context_and_never_copies_hindsight(monkeypatch,local):
    received=[]
    def classify(conn,event):
        assert event['payload']['context']=='private fixture context'
        return 'local_only'
    monkeypatch.setattr(m.privacy,'classify_event',classify)
    monkeypatch.setattr(m.events,'record_events',lambda events,conn:received.extend(events) or {'inserted':1,'event_ids':['fixture']})
    out=m.retain('a private fact','private fixture context',caller='codex')
    assert received[0]['privacy_class']=='local_only'
    assert out['cognitive_projection']=='not_requested' and out['search_projection']=='pending_indexer'
    assert 'private fixture context' not in json.dumps(out)


def test_reflect_uses_router_and_redacts_question_before_model(monkeypatch,local):
    monkeypatch.setattr(m.privacy,'classify',lambda *a,**kw:('redacted_cloud',[]))
    monkeypatch.setattr(m.search,'search',lambda *a,**kw:[row()])
    calls=[]
    def chat(messages,**kw): calls.append((messages,kw)); return {'content':'A cited synthesis [event:fixture]','model':'router-selected'}
    monkeypatch.setattr(m.llm,'chat',chat)
    out=m.reflect('Email fixture@example.test about this project')
    assert out['model_called'] is True
    assert 'fixture@example.test' not in json.dumps(calls)
    assert calls[0][1]['poste']=='memory_extraction' and calls[0][1]['budget']=='recurring'
    assert calls[0][1]['privacy_class']=='redacted_cloud'
    assert 'Hindsight reflect' in out['notice']


def test_reflect_empty_evidence_does_not_call_model(monkeypatch,local):
    monkeypatch.setattr(m.search,'search',lambda *a,**kw:[])
    out=m.reflect('a project')
    assert out['model_called'] is False


def test_mcp_memory_facades_send_payload_on_stdin_not_argv(monkeypatch):
    tree=ast.parse(Path('/opt/walter-core/server.py').read_text())
    selected=[]
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in {'_agent_memory','memory_recall','memory_retain','memory_reflect'}:
            node.decorator_list=[];selected.append(node)
    seen=[]
    class Subprocess:
        @staticmethod
        def run(args,**kwargs):
            seen.append((args,kwargs));return type('Result',(),{'returncode':0,'stdout':'{"status":"ok"}','stderr':''})()
    ns={'subprocess':Subprocess,'json':json,'CLIENT_TAG':'codex','WALTER_MEMORY':['walter-memory']}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'<memory facade>','exec'),ns)
    ns['memory_recall']('fixture query'); ns['memory_retain']('fixture private fact'); ns['memory_reflect']('fixture question')
    assert len(seen)==3
    for args,kw in seen:
        assert args==['walter-memory','agent-memory']
        assert 'fixture' in kw['input'] and kw['capture_output'] and kw['text']
        assert json.loads(kw['input'])['caller']=='codex'
