"""P1 ([thread_blocks], owner 26/11): an existing thread chosen with too little confidence brings none of its blocks
to the pack, for the listed runtimes only. The plan keeps its thread (the run and Memory attach it); the memory
retrieval and the visible conversation do not depend on it."""
import json
import sys
import types

import pytest

from walter_context import config
from walter_context.plan import ContextPlan, ThreadChoice
from walter_context.preflight import __main__ as cli


def _toml(tmp_path, body):
    p = tmp_path / "walter-context.toml"
    p.write_text(body)
    return p


def _plan(thread):
    return ContextPlan(turn_id="t", thread=thread, act="continue", level="L2").validate()


def test_settings_default_to_off_and_refuse_a_threshold_above_one(tmp_path):
    assert config.thread_blocks_settings(_toml(tmp_path, "")) == {"runtimes": [], "min_confidence": 0.0}
    assert config.thread_blocks_settings(_toml(tmp_path, '[thread_blocks]\nruntimes = ["walter"]\nmin_confidence = 0.8\n')) \
        == {"runtimes": ["walter"], "min_confidence": 0.8}
    with pytest.raises(ValueError):
        config.thread_blocks_settings(_toml(tmp_path, "[thread_blocks]\nmin_confidence = 8\n"))


@pytest.fixture
def walter_only(monkeypatch):
    monkeypatch.setattr(config, "thread_blocks_settings", lambda path=None: {"runtimes": ["walter"], "min_confidence": 0.8})


def test_an_unsure_thread_is_withheld_for_walter_and_put_back_by_the_caller(walter_only):
    chosen = ThreadChoice(id="subject:a", confidence=0.6, alternates=["subject:b"])
    p = _plan(chosen)
    trace = cli._thread_blocks(p, "walter")
    assert p.thread.id is None and p.thread.new and p.thread.alternates == []
    assert trace["withheld"] == "subject:a" and trace["confidence"] == 0.6 and trace["min_confidence"] == 0.8
    assert trace["_chosen"] is chosen


@pytest.mark.parametrize("runtime,thread", [
    ("claude_code", ThreadChoice(id="subject:a", confidence=0.6)),      # P1 is for Walter only (bench 26/11)
    ("walter", ThreadChoice(id="subject:a", confidence=0.8)),           # sure enough
    ("walter", ThreadChoice(id="subject:a", confidence=None)),          # no confidence said: kept
    ("walter", ThreadChoice(id=None, new=True, confidence=0.3)),        # already a new thread
])
def test_other_runtimes_sure_threads_and_new_threads_are_untouched(walter_only, runtime, thread):
    p = _plan(thread)
    assert cli._thread_blocks(p, runtime) is None and p.thread is thread


def test_unreadable_settings_leave_the_thread(monkeypatch):
    def boom(path=None):
        raise OSError("gone")
    monkeypatch.setattr(config, "thread_blocks_settings", boom)
    p = _plan(ThreadChoice(id="subject:a", confidence=0.1))
    assert cli._thread_blocks(p, "walter") is None and p.thread.id == "subject:a"


def _handle(monkeypatch, tmp_path, runtime, confidence):
    from walter_context import retrieval
    seen = {}
    plan_obj = _plan(ThreadChoice(id="subject:a", confidence=confidence))
    monkeypatch.setattr(cli, "_STATE", [tmp_path])
    monkeypatch.setattr(cli, "subjects", lambda d: ([], None, None))
    monkeypatch.setattr(cli, "last_exchange", lambda key, message: None)
    monkeypatch.setattr(cli, "previous_profile", lambda key: None)
    monkeypatch.setattr(cli, "run", lambda req, **kw: plan_obj)

    def gather(plan, msg, **kw):
        seen["thread"] = plan.thread.id
        return [retrieval.Block("memory", 4, "souvenirs")], []
    monkeypatch.setattr(retrieval, "gather", gather)
    d = {"message": "on reprend où on en était ?", "runtime": runtime, "session_id": f"{runtime}/vm/s1"}
    plan, row = cli.handle(d, shadow=False, want_pack=True)
    return plan, row, seen, plan_obj


def test_handle_reads_the_pack_without_the_unsure_thread_and_answers_with_it(walter_only, monkeypatch, tmp_path):
    plan, row, seen, plan_obj = _handle(monkeypatch, tmp_path, "walter", 0.6)
    assert seen["thread"] is None                                   # the pack: as for a new thread
    assert plan["thread"] == {"id": "subject:a", "new": False, "confidence": 0.6, "alternates": []}
    assert plan_obj.thread.id == "subject:a"                        # put back for the run and the readings
    assert row["thread_blocks"] == {"withheld": "subject:a", "confidence": 0.6, "min_confidence": 0.8}
    assert row["pack"]["thread"] is None                            # the journal says what the pack was read for
    ContextPlan.from_dict(plan)                                      # the answered plan is still the contract's
    rows = [json.loads(x) for f in tmp_path.glob("preflight-*.jsonl") for x in f.read_text().splitlines()]
    assert rows[-1]["thread_blocks"]["withheld"] == "subject:a"


def test_handle_leaves_claude_code_and_sure_threads_alone(walter_only, monkeypatch, tmp_path):
    for runtime, conf in (("claude_code", 0.6), ("walter", 0.9)):
        plan, row, seen, _ = _handle(monkeypatch, tmp_path, runtime, conf)
        assert seen["thread"] == "subject:a" and "thread_blocks" not in row and plan["thread"]["id"] == "subject:a"
        assert row["pack"]["thread"] == "subject:a"
