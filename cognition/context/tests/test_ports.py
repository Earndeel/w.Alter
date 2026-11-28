"""Host-independent policy and port regression tests."""
import importlib.util
import os
import sys
import types
from contextlib import contextmanager
from pathlib import Path

from walter_context import Session, load
from walter_context.compress.checkpoint import plan, summarize
from walter_context.recover import recover
from test_core import conversation

ROOT = Path(__file__).resolve().parent.parent


def test_checkpoint_preserves_live_and_previous_turn_under_pressure():
    messages = conversation(7, out_chars=12000)
    p = plan(messages, measured_tokens=200000)
    assert p['needed'] and messages[p['end']]['role'] == 'user'
    assert messages[p['end']]['content'].startswith('request 5')
    assert not plan(conversation(2), measured_tokens=200000, force=True)['needed']


def test_checkpoint_summary_retains_original_refs_and_reduces_tool_traffic():
    from walter_context.compress.layers import record
    messages = conversation(4)
    result = summarize(messages)
    from walter_context.compress.wire import strip_injected
    # the owner's own text in full; Walter's per-turn injections (<memory-context>…) are not the owner's words
    assert all(strip_injected(m['content']).strip() in result['content'] for m in messages if m['role']=='user')
    assert '<memory-context>' not in result['content']
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


def test_quality_replay_rejects_a_chain_containing_non_cloud_events():
    from bench.replay import messages
    class Conn:
        def execute(self,*args): return self
        def fetchall(self): return [{'privacy_class':'local_only','text':'private fixture'}]
    assert messages(Conn(),[{'session_id':'fixture'}],cloud_safe=True) == ([],[])


def test_pressure_inside_a_single_live_turn_asks_to_trim_tool_outputs():
    """2026-11-07: a one-turn deep research overflowed; nothing precedes the live turn, so trimming is the only move."""
    live = conversation(1, out_chars=12000)
    p = plan(live, measured_tokens=200000)
    assert not p['needed'] and p['prune_tools']
    assert not plan(live, measured_tokens=1000)['prune_tools']
