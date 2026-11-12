"""Socle A4 (2026-11-11): execution experience becomes retrievable memory — an episode for failed runs with tool
errors, the episode outcome (deterministic, then the model's JSON merged defensively), the g1 `experience` derived
item written once per version and superseded by the next, the objective updated from the outcome, experience() and
the Context layers. Throwaway DB only; no real model call (llm.chat monkeypatched)."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import context, episodes, runs
from walter_memory.db import connect

RT = "pytest-exp"


def _cleanup():
    with connect() as c:
        ids = [str(r["run_id"]) for r in c.execute("select run_id from runs.runs where origin->>'runtime' = %s", (RT,))]
        items = [r["item_id"] for r in c.execute(
            "select item_id::text from core.derived_items where derived_by = %s and attributes->>'run_id' = any(%s)",
            (episodes.EXPERIENCE_BY, ids))]
        c.execute("delete from bus.events where subject = any(%s)", (ids + items,))
        c.execute("delete from search.chunks where kind = 'derived' and ref_id::text = any(%s)", (items,))
        c.execute("delete from core.derived_items where item_id::text = any(%s)", (items,))
        c.execute("delete from runs.episodes where run_id::text = any(%s)", (ids,))
        c.execute("delete from runs.links where run_id::text = any(%s)", (ids,))
        c.execute("delete from runs.task_runs where run_id::text = any(%s)", (ids,))
        c.execute("delete from runs.tasks where run_id::text = any(%s)", (ids,))
        c.execute("update runs.runs set parent_run_id = null where run_id::text = any(%s)", (ids,))
        c.execute("delete from runs.runs where run_id::text = any(%s)", (ids,))
        c.execute("delete from walter_logs.events where session_id like %s", (f"{RT}/%",))
        c.execute("delete from walter_logs.sessions where session_id like %s", (f"{RT}/%",))


@pytest.fixture(autouse=True)
def cleanup():
    _cleanup()
    yield
    _cleanup()


def sid():
    return f"{RT}/vm/{uuid.uuid4()}"


def thread():
    return f"subject:pytest-{uuid.uuid4().hex[:8]}"


def tool_trace(session, n_ok=1, error="Error: permission denied while writing /etc/x (token <secret:redacted>)"):
    now = datetime.now(timezone.utc)
    evs = []
    for i in range(n_ok):
        evs += [{"type": "tool/call", "at": now, "text": "{}", "tool": "Read", "call_id": f"ok{i}"},
                {"type": "tool/result", "at": now, "text": "fine", "tool": "Read", "call_id": f"ok{i}", "status": "ok"}]
    if error:
        evs += [{"type": "tool/call", "at": now, "text": "{\"cmd\": \"cp\"}", "tool": "Bash", "call_id": "e1"},
                {"type": "tool/result", "at": now, "text": error, "call_id": "e1", "status": "error"}]
    runs.trace(session, evs, runtime=RT, native_id=session.rsplit("/", 1)[-1])


def failed_run(th=None, session=None, objective=False):
    session = session or sid()
    a = runs.start(origin={"channel": "owner", "runtime": RT, "session_id": session}, goal="installe le service X",
                   started_at=datetime.now(timezone.utc) - timedelta(seconds=30))
    if objective:
        runs.update(a, thread_id=th, act="new", requested={"task": "coding", "level": "L2"})
    elif th:
        runs.update(a, thread_id=th)
    tool_trace(session)
    runs.end(a, "failed", outcome={"status": "failed", "error": {"kind": "tool_error", "message": "cp refused"}})
    return a


def fake_chat(monkeypatch, payload):
    calls = []

    def chat(messages, **kw):
        calls.append(json.loads(messages[1]["content"]))
        return {"content": payload if isinstance(payload, str) else json.dumps(payload), "model": "fake/model"}
    from walter_memory import llm
    monkeypatch.setattr(llm, "chat", chat)
    return calls


def test_a_failed_run_with_tool_errors_gets_an_episode_with_its_errors():
    a = failed_run()
    ep = episodes.build(a, summarise=False)
    tools = ep["evaluation"]["technical"]["tools"]
    assert ep["version"] == 1 and ep["evaluation"]["technical"]["status"] == "failed"
    assert tools == {"calls": 2, "errors": 1, "failing": ["Bash"]}
    o = ep["outcome"]
    assert o["status"] == "failed" and o["lessons"] == [] and o["solutions"] == []
    whats = [e["what"] for e in o["errors"]]
    assert whats[0] == "tool_error" and "outil Bash" in whats
    assert "sk-proj-AbCd" not in json.dumps(o)                                # tool excerpt masked
    with connect() as c:
        stored = c.execute("select outcome from runs.episodes where run_id = %s", (a,)).fetchone()["outcome"]
    assert stored == o


def test_a_run_without_anything_is_trivial_and_marked_so_the_catch_up_skips_it():
    a = runs.start(origin={"channel": "owner", "runtime": RT, "session_id": sid()}, goal="bonjour")
    runs.end(a)
    assert episodes.build(a, summarise=False) == {"skipped": "trivial run"}
    with connect() as c:
        assert c.execute("select 1 from runs.links where run_id = %s and kind = 'episode' and ref = 'trivial'",
                         (a,)).fetchone()
    b = failed_run()
    built = [x.get("run_id") for x in episodes.pending(limit=200)]
    assert b in built and a not in built


def test_the_model_json_completes_the_outcome_but_never_turns_a_failure_into_success(monkeypatch):
    calls = fake_chat(monkeypatch, "```json\n" + json.dumps({
        "summary": "L'installation a échoué sur une copie refusée.", "status": "achieved",
        "errors": [{"what": "copie", "why": "droits"}], "lessons": ["vérifier les droits avant cp"],
        "solutions": [], "pending": ["relancer avec sudo"]}) + "\n```")
    a = failed_run()
    ep = episodes.build(a)
    assert calls and calls[0]["deterministic_outcome"]["status"] == "failed"
    o = ep["outcome"]
    assert o["status"] == "failed" and o["lessons"] == ["vérifier les droits avant cp"]
    assert o["pending"] == ["relancer avec sudo"] and {"what": "copie", "why": "droits"} in o["errors"]
    assert ep["summary"].startswith("L'installation")
    fake_chat(monkeypatch, "pas du JSON du tout")                              # unparseable → deterministic stands
    b = failed_run()
    ep = episodes.build(b)
    assert ep["summary"] == "pas du JSON du tout" and ep["outcome"]["lessons"] == []


def test_experience_item_is_written_once_per_version_and_superseded_by_the_next(monkeypatch):
    th = thread()
    a = failed_run(th)
    v1 = episodes.build(a, summarise=False)["experience"]
    assert v1["published"]
    run = runs.show(a)["run"]
    again = episodes.publish_experience(run, 1, None, episodes.latest(a)["outcome"])
    assert again == {"published": False, "duplicate": True}
    b = runs.start(origin={"channel": "owner", "runtime": RT, "session_id": sid()}, goal="non, autrement")
    runs.update(b, thread_id=th, act="correct"); runs.end(b)
    out = episodes.build(b, summarise=False)                                  # trivial correction re-versions a
    assert out["parent"]["version"] == 2
    with connect() as c:
        rows = c.execute("""select item_id::text, status, lineage_id::text, generation, epistemic, stage, kind,
                                   source_refs, valid_to, attributes
                            from core.derived_items where derived_by = %s and attributes->>'run_id' = %s
                            order by created_at""", (episodes.EXPERIENCE_BY, a)).fetchall()
    assert [r["status"] for r in rows] == ["superseded", "derived"] and rows[0]["valid_to"]
    assert rows[0]["lineage_id"] == rows[1]["lineage_id"]
    cur = rows[1]
    assert (cur["generation"], cur["epistemic"], cur["stage"], cur["kind"]) == ("g1", "agent_reported", "executed", "experience")
    assert cur["source_refs"]["thread"] == th and cur["attributes"]["version"] == 2
    assert rows[0]["attributes"]["superseded_by"] == cur["item_id"]


def test_the_objective_follows_the_episode_outcome(monkeypatch):
    th = thread()
    fake_chat(monkeypatch, {"summary": "Copie refusée.", "status": "partial", "errors": [], "lessons": [],
                            "solutions": ["contourné avec un dossier temporaire"], "pending": ["finir la config"]})
    a = failed_run(th, objective=True)
    tid = runs.objective_of_run(a)
    ep = episodes.build(a)
    assert ep["task"]["status"] == "open"                                     # a failure keeps it open: retry plausible
    t = runs.task_get(tid)
    assert t["progress"]["pending"] == ["finir la config"] and t["last_outcome"].startswith("partial: tool_error")
    fake_chat(monkeypatch, {"summary": "Service installé.", "status": "achieved", "errors": [], "lessons": [],
                            "solutions": [], "pending": []})
    s = sid()
    b = runs.start(origin={"channel": "owner", "runtime": RT, "session_id": s}, goal="réessaie",
                   started_at=datetime.now(timezone.utc) - timedelta(seconds=30))
    runs.update(b, thread_id=th, act="continue")
    tool_trace(s, n_ok=6, error=None)
    runs.end(b, "ended", outcome={"status": "ok"})
    ep = episodes.build(b)
    assert ep["outcome"]["status"] == "achieved" and ep["task"]["status"] == "done"
    assert ep["experience"] == {"published": False, "superseded": 0}         # a plain success: nothing to learn
    done = runs.task_get(tid)
    assert done["status"] == "done" and done["attempts"] == 2 and done["result"]["refs"]["runs"] == [b]


def test_experience_serves_the_thread_failures_first_in_the_binding_shape(monkeypatch):
    th = thread()
    fake_chat(monkeypatch, {"summary": "ok", "status": "achieved", "errors": [], "lessons": [], "solutions": [],
                            "pending": []})
    a = failed_run(th)
    episodes.build(a, summarise=False)
    s = sid()
    b = runs.start(origin={"channel": "owner", "runtime": RT, "session_id": s}, goal="autre essai",
                   started_at=datetime.now(timezone.utc) - timedelta(seconds=30))
    runs.update(b, thread_id=th); tool_trace(s, n_ok=6, error=None); runs.end(b)
    episodes.build(b)
    items = episodes.experience(thread_id=th, limit=5)
    assert [i["run_id"] for i in items] == [a, b]                             # the failure first, though older
    assert set(items[0]) >= {"at", "run_id", "status", "summary", "errors", "lessons", "solutions", "pending"}
    assert items[0]["status"] == "failed" and items[1]["status"] == "achieved"


def test_context_has_bounded_tasks_and_experience_layers():
    th = thread()
    failed_run(th, objective=True)
    assert runs.tasks_list(thread_id=th)
    with connect() as c:
        run_id = str(c.execute("select run_id from runs.runs where thread_id = %s", (th,)).fetchone()["run_id"])
    episodes.build(run_id, summarise=False)
    zero = {k: 0 for k in context.DEFAULT_BUDGET}
    res = context.get_context("installe le service X", budget={**zero, "tasks": 250, "experience": 350},
                              include_profile=False, thread_id=th)
    assert "tasks" in res["sections"] and "experience" in res["sections"]
    assert "installe le service X" in res["sections"]["tasks"] and "a échoué" in res["sections"]["experience"]
    assert res["trace"]["sections"]["tasks"]["tokens"] <= 250 and res["trace"]["sections"]["experience"]["tokens"] <= 350
    assert "## Tâches de Monsieur" in res["text"] and "## Expérience" in res["text"]
    tiny = context.get_context("installe le service X", budget={**zero, "tasks": 5, "experience": 5},
                               include_profile=False, thread_id=th)
    assert "tasks" not in tiny["sections"] and tiny["trace"]["sections"]["tasks"]["tokens"] == 0
    # the session alone leads to the thread (another consumer that only knows its session)
    with connect() as c:
        sess = c.execute("select origin->>'session_id' s from runs.runs where run_id = %s", (run_id,)).fetchone()["s"]
    assert context.thread_of_session(RT, sess.rsplit("/", 1)[-1]) == th
    off = context.get_context("x", budget={**zero}, include_profile=False, thread_id=th)
    assert "tasks" not in off["trace"]["sections"]


def test_an_interrupted_run_suspends_its_objective_and_a_budget_stop_keeps_it_open():
    th = thread()
    s = sid()
    a = runs.start(origin={"channel": "owner", "runtime": RT, "session_id": s}, goal="refonds la page d'accueil")
    tid = runs.update(a, thread_id=th, act="new", requested={"task": "coding", "level": "L2"})["task_id"]
    runs.end(a, "cancelled", outcome={"status": "interrupted", "error": {"kind": "engine_restart", "message": "restart"}})
    ep = episodes.build(a, summarise=False)
    assert ep["task"]["status"] == "suspended" and ep["outcome"]["status"] != "achieved"
    assert ep["outcome"]["errors"][0]["what"].startswith("interrompu")
    t = runs.task_get(tid)
    assert t["status"] == "suspended" and t["last_outcome"].startswith("unknown: interrompu")
    b = runs.start(origin={"channel": "owner", "runtime": RT, "session_id": s}, goal="continue")
    assert runs.update(b, thread_id=th, act="continue")["task"] == "reopened"
    runs.end(b, "failed", outcome={"status": "failed", "error": {"kind": "budget", "message": "turn cap"}})
    ep = episodes.build(b, summarise=False)
    assert ep["task"]["status"] == "open" and "budget" in runs.task_get(tid)["last_outcome"]
