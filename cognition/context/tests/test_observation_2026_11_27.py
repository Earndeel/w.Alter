"""Observation 2026-11-27: a level is a retrieval depth, not a duty to fill every block; the act is about the visible
conversation, the thread about persistence."""
import json
from pathlib import Path

from walter_context import retrieval
from walter_context.plan import ContextPlan, ThreadChoice
from walter_context.preflight import ACT_CRITERIA

ROOT = Path(__file__).resolve().parents[1]


def mk(act="new", thread=None, new=True, level="L1", personal=()):
    return ContextPlan(turn_id="t", thread=ThreadChoice(id=thread, new=new), act=act, level=level, personal=list(personal))


def test_continues_follows_the_visible_exchange_or_the_thread():
    assert not retrieval.continues(mk())                                  # a new request, no thread
    assert retrieval.continues(mk(act="continue"))                       # a follow-up of an L0 exchange, no thread
    assert retrieval.continues(mk(thread="subject:a", new=False))        # joins a stored thread


def test_working_state_only_when_the_message_carries_on(monkeypatch):
    seen = []

    class Ctx:
        @staticmethod
        def get_context(message, budget, **kw):
            seen.append(budget["working"])
            return {"text": ""}
    import sys
    import types
    monkeypatch.setitem(sys.modules, "walter_memory.context", Ctx)
    monkeypatch.setitem(sys.modules, "walter_memory", types.SimpleNamespace(context=Ctx))
    retrieval.session_state(mk(), "m", "walter/vm/s")
    retrieval.session_state(mk(act="continue"), "m", "walter/vm/s")
    assert seen[0] == 0 and seen[1] > 0


def test_other_objectives_only_when_the_answer_depends_on_tasks():
    calls = []

    def fetch(route, body):
        calls.append(body)
        return {"tasks": [{"task_id": "x", "status": "open", "goal": "g", "thread_id": "other"}]}
    assert retrieval.tasks(mk(), fetch, session_key="walter/vm/s") is None and calls == []
    assert retrieval.tasks(mk(level="L0", personal=["tasks"]), fetch, session_key="walter/vm/s") is None
    b = retrieval.tasks(mk(personal=["tasks"]), fetch, session_key="walter/vm/s")
    assert b is not None and calls[-1].get("asking_session") == "walter/vm/s"


def test_act_question_is_about_the_previous_exchange_not_the_threads():
    d = json.loads((ROOT / "manifest" / "decisions.json").read_text())["signals"]["act"]["question"]
    for criteria in (d["criteria"], ACT_CRITERIA):
        assert "threads covers" not in criteria["new"] and "previous exchange" in criteria["new"]
        assert "stored thread" in criteria["continue"]
    assert "asked separately" in d["instructions"]
