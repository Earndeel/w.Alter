"""Run with the installed Hermes interpreter and real public provider loader."""
import json
from pathlib import Path
import shutil
import sys
import threading

import pytest

HERMES = Path('/root/.hermes/hermes-agent')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERMES))
sys.path.insert(0, str(ROOT))
from hermes_constants import set_hermes_home_override, reset_hermes_home_override
from walter_memory import client


@pytest.fixture
def homes(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path/'a'))
    monkeypatch.setattr(client, 'configured', lambda: True)
    for name in ('a', 'b'):
        home=tmp_path/name; plugin=home/'plugins/walter-memory';plugin.mkdir(parents=True)
        shutil.copyfile(ROOT/'ports/hermes/__init__.py', plugin/'__init__.py')
        (plugin/'plugin.yaml').write_text('name: walter-memory\nversion: 1.0.0\ndescription: Walter memory port\n')
        (home/'config.yaml').write_text('memory:\n  provider: walter-memory\n')
    return tmp_path/'a', tmp_path/'b'


def load(home):
    from plugins.memory import load_memory_provider
    token=set_hermes_home_override(home)
    provider=load_memory_provider('walter-memory', register_skills=False)
    assert provider is not None
    provider.initialize('session', hermes_home=str(home))
    return token, provider


def response(text):
    return {'status':'ok','text':text,'records':[{'ref':'event:fixture'}]}


def test_real_loader_recall_tools_and_no_duplicate_turn_write(homes, monkeypatch):
    calls=[]
    monkeypatch.setattr(client,'call',lambda method,args,**kw:calls.append((method,args,kw)) or response(args.get('query','note')))
    token,provider=load(homes[0])
    try:
        assert 'question' in provider.prefetch('question',session_id='session')
        assert provider.recall_status().count==1
        provider.sync_turn('user','assistant',session_id='session')
        assert len(calls)==1
        names={s['name'] for s in provider.get_tool_schemas()}
        assert names=={'memory_recall','memory_retain','memory_reflect'}
        assert json.loads(provider.handle_tool_call('memory_retain',{'content':'fixture'}))['status']=='ok'
        assert calls[-1][0]=='retain'
        assert json.loads(provider.handle_tool_call('memory_retain',{'content':'fixture','caller':'fake'}))['status']=='error'
    finally:
        provider.shutdown();reset_hermes_home_override(token)


def test_real_loader_profile_scope_a_b_a(homes, monkeypatch):
    monkeypatch.setattr(client,'call',lambda method,args,**kw:response(args['query']))
    token_a,first=load(homes[0])
    try:
        assert 'first' in first.prefetch('first')
        token_b,second=load(homes[1])
        try:
            with pytest.raises(PermissionError):first.prefetch('wrong scope')
            assert 'second' in second.prefetch('second')
        finally:
            second.shutdown();reset_hermes_home_override(token_b)
        assert 'again' in first.prefetch('again')
    finally:
        first.shutdown();reset_hermes_home_override(token_a)


def test_late_background_result_cannot_cross_session(homes, monkeypatch):
    started=threading.Event();release=threading.Event()
    def call(method,args,**kw):
        if args['query']=='old':started.set();release.wait(timeout=5)
        return response(args['query'])
    monkeypatch.setattr(client,'call',call)
    token,provider=load(homes[0])
    try:
        provider.queue_prefetch('old',session_id='session')
        assert started.wait(timeout=2)
        provider.on_session_switch('next')
        release.set();provider._worker.join(timeout=2)
        assert provider._pending is None
        assert provider.prefetch('old',session_id='session')==''
        assert 'new' in provider.prefetch('new',session_id='next')
        provider.shutdown()
        assert provider.prefetch('new',session_id='next')==''
    finally:
        release.set();reset_hermes_home_override(token)


def test_empty_and_failed_recall_clear_indicator(homes, monkeypatch):
    monkeypatch.setattr(client,'call',lambda *a,**kw:response('fixture'))
    token,provider=load(homes[0])
    try:
        assert provider.prefetch('one')
        monkeypatch.setattr(client,'call',lambda *a,**kw:{'status':'error'})
        assert provider.prefetch('two')==''
        assert provider.recall_status() is None
    finally:
        provider.shutdown();reset_hermes_home_override(token)
