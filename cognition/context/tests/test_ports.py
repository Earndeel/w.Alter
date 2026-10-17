"""Host-independent policy and Hermes public-interface regression tests."""
import importlib.util
import sys
import types
from contextlib import contextmanager
from pathlib import Path

from walter_context import Session, load
from walter_context.checkpoint import plan, summarize
from walter_context.journal import recover
from test_core import conversation

ROOT = Path(__file__).resolve().parent.parent


def test_checkpoint_preserves_live_and_previous_turn_under_pressure():
    messages = conversation(7, out_chars=12000)
    p = plan(messages, measured_tokens=200000)
    assert p['needed'] and messages[p['end']]['role'] == 'user'
    assert messages[p['end']]['content'].startswith('request 5')
    assert not plan(conversation(2), measured_tokens=200000, force=True)['needed']


def test_checkpoint_summary_is_same_shared_record_as_projection():
    from walter_context.layers import record
    messages = conversation(4)
    result = summarize(messages)
    assert result['content'] == record(messages[1:], load().projection, None)['content']
    assert result['output_tokens'] < result['input_tokens']
    assert 'call_0_0' in result['content']


def test_smaller_host_window_caps_common_profile():
    session = Session(model='gpt-6.1-sol')
    session.set_budget(16000)
    assert session.profile.hard_budget == 16000
    assert session.profile.effective_budget == int(16000 * load().policy.emergency_share)
    session.set_budget(0)
    assert session.profile.hard_budget > 16000


def test_recovery_privilege_requires_exact_session_and_prefers_own_collision(monkeypatch):
    calls = []
    class Cursor:
        def __init__(self, value): self.value = value
        def fetchone(self): return self.value
    class Conn:
        def execute(self, query, params):
            calls.append(params)
            return Cursor({'session_id': params[1] if len(params)>1 else 'hermes/main/other', 'seq': 7})
    @contextmanager
    def connection(): yield Conn()
    privacy = []
    logs = types.ModuleType('walter_memory.logs')
    def get(conn, sid, seq, limit):
        privacy.append((sid, limit)); return {'text':'safe fixture', 'session_id':sid}
    logs.get = get
    package = types.ModuleType('walter_memory'); package.logs = logs
    db = types.ModuleType('walter_memory.db'); db.connection = connection
    monkeypatch.setitem(sys.modules,'walter_memory',package)
    monkeypatch.setitem(sys.modules,'walter_memory.db',db)
    monkeypatch.setitem(sys.modules,'walter_memory.logs',logs)
    recover('same-call',own='hermes/main/')
    assert privacy[-1][1] == 'cloud_allowed'
    recover('same-call',own='hermes/main/mine')
    assert calls[-1] == ('same-call','hermes/main/mine')
    assert privacy[-1] == ('hermes/main/mine','local_only')


def test_hermes_public_port_budget_reset_and_usage():
    # Run in the installed Hermes venv, importing only its public base contract.
    sys.path.insert(0,'/root/.hermes/hermes-agent')
    spec = importlib.util.spec_from_file_location('walter_context_test_port',ROOT/'ports/hermes/__init__.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine = module.WalterContextEngine()
    engine.update_model('gpt-6.1-sol',16000)
    engine.on_session_start('fixture',hermes_home='/root/.hermes/profiles/wild')
    assert engine._profile == 'wild'
    assert engine._session.profile.hard_budget == 16000
    source = conversation(4)
    import copy
    original = copy.deepcopy(source)
    engine.select_context(source,budget_tokens=12000)
    assert source == original and engine._session.profile.hard_budget == 12000
    engine.update_from_response({'input_tokens': 400, 'output_tokens': 50})
    assert engine.last_prompt_tokens == 400 and engine.last_completion_tokens == 50
    engine.on_session_start('other')
    assert engine._session.calls == 0


def test_quality_replay_rejects_a_chain_containing_non_cloud_events():
    from bench.replay import messages
    class Conn:
        def execute(self,*args): return self
        def fetchall(self): return [{'privacy_class':'local_only','text':'private fixture'}]
    assert messages(Conn(),[{'session_id':'fixture'}],cloud_safe=True) == ([],[])
