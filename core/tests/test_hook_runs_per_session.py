"""One DSH web process serves several sessions: a run is started, interrupted and ended per session, never by the
process record of another session (2026-11-07: a Bitcoin turn's Stop closed the next session's run → walter-llm 409)."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def hook(monkeypatch, tmp_path):
    monkeypatch.setenv("WALTER_INSTANCE", str(tmp_path))
    monkeypatch.delenv("WALTER_RUN_ID", raising=False)
    monkeypatch.setenv("WALTER_EPISODES", "off")
    sys.path.insert(0, str(ROOT / "hooks"))
    import runctx
    monkeypatch.setattr(runctx, "FALLBACK", tmp_path / "fallback")
    ended, superseded, ids = [], [], iter(f"run-{i}" for i in range(100))
    runs = types.SimpleNamespace(
        start=lambda **k: next(ids), routing=lambda *a, **k: None, sweep=lambda: None,
        safe=lambda fn, *a, **k: fn(*a, **k),
        supersede=lambda session, run_id, status="cancelled": superseded.append((session, run_id)) or [],
        end=lambda run_id, status="ended", costs=None: ended.append((run_id, status)),
        end_open=lambda session, status="ended": ended.append((f"open:{session}", status)) or f"open:{session}")
    pkg = types.ModuleType("walter_memory"); pkg.runs = runs
    monkeypatch.setitem(sys.modules, "walter_memory", pkg)
    monkeypatch.setitem(sys.modules, "walter_memory.runs", runs)
    spec = importlib.util.spec_from_file_location("walter_hook_runs", ROOT / "hooks" / "walter_hook.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_privacy", lambda: types.SimpleNamespace(detect=lambda text: []))
    mod.ended = ended
    mod.superseded = superseded
    yield mod
    sys.path.remove(str(ROOT / "hooks"))


def test_another_sessions_stop_does_not_end_the_newest_run(hook):
    a = hook.run_start("dsh", "dsh/vm/session-a", "Quel est le prix du Bitcoin ?", record_pid=4242)
    b = hook.run_start("dsh", "dsh/vm/session-b", "Retrouve le premier événement", record_pid=4242)
    assert (a, "cancelled") not in hook.ended            # session a is still working: not interrupted by b
    hook.run_end("dsh", "dsh/vm/session-a", record_pid=4242)
    assert (b, "ended") not in hook.ended and ("open:dsh/vm/session-a", "ended") in hook.ended
    hook.run_end("dsh", "dsh/vm/session-b", record_pid=4242)
    assert (b, "ended") in hook.ended


def test_a_new_message_in_the_same_session_interrupts_its_own_run(hook):
    a = hook.run_start("dsh", "dsh/vm/session-a", "premier", record_pid=4243)
    hook.run_start("dsh", "dsh/vm/session-a", "second", record_pid=4243)
    assert (a, "cancelled") in hook.ended


def test_after_a_harness_restart_the_sessions_older_open_run_is_superseded(hook):
    # the engine restarted mid-turn: the new process has no record of the old run, Memory closes it by session
    b = hook.run_start("dsh", "dsh/vm/session-a", "après redémarrage", record_pid=5555)
    assert ("dsh/vm/session-a", b) in hook.superseded
