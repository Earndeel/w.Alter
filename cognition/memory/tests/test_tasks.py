"""Socle A3 (2026-11-11): the owner's durable task (runs.tasks kind objective) carried by the Run Plane, the run's
structured outcome, the gateway routes, and triage decisions that failed never being final. Throwaway DB only; runs
of origin.runtime 'pytest-tasks' and everything they wrote are removed at the end."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from walter_memory import gateway, runs, triage
from walter_memory.db import connect

RT = "pytest-tasks"


def _cleanup():
    with connect() as c:
        ids = [str(r["run_id"]) for r in c.execute("select run_id from runs.runs where origin->>'runtime' = %s", (RT,))]
        if ids:
            c.execute("delete from bus.events where source = 'runs' and subject = any(%s)", (ids,))
            c.execute("delete from runs.episodes where run_id::text = any(%s)", (ids,))
            c.execute("delete from runs.links where run_id::text = any(%s)", (ids,))
            c.execute("delete from runs.task_runs where run_id::text = any(%s)", (ids,))
            c.execute("update runs.tasks set parent_task_id = null where run_id::text = any(%s)", (ids,))
            c.execute("delete from runs.tasks where run_id::text = any(%s)", (ids,))
            c.execute("update runs.runs set parent_run_id = null where run_id::text = any(%s)", (ids,))
            c.execute("delete from runs.runs where run_id::text = any(%s)", (ids,))
        c.execute("delete from triage.decisions where thread_id like 'pytest-tasks%'")


@pytest.fixture(autouse=True)
def cleanup():
    _cleanup()
    yield
    _cleanup()


def origin(sid=None, channel="owner"):
    return {"channel": channel, "runtime": RT, "session_id": sid or f"{RT}/vm/{uuid.uuid4()}"}


def thread():
    return f"subject:pytest-{uuid.uuid4().hex[:8]}"


CODING = {"task": "coding", "level": "L1"}
CHAT = {"task": "general", "level": "L1"}


def bus(type_, run_id):
    with connect() as c:
        return c.execute("select payload from bus.events where type = %s and subject = %s order by id",
                         (type_, run_id)).fetchall()


def test_an_actionable_new_request_opens_one_objective_and_a_chat_opens_none():
    th = thread()
    a = runs.start(origin=origin(), goal="corrige le bug du connecteur Beeper")
    out = runs.update(a, thread_id=th, act="new", requested=CODING)
    assert out["task"] == "opened"
    again = runs.update(a, thread_id=th, act="new", requested=CODING)          # the preflight attaches twice
    assert again == {"task_id": out["task_id"], "task": "linked"}
    [t] = runs.tasks_list(thread_id=th)
    assert set(t) == {"task_id", "goal", "status", "thread_id", "updated_at", "progress", "attempts", "last_outcome"}
    assert t["status"] == "open" and t["attempts"] == 1 and t["goal"].startswith("corrige")
    assert len(bus("task.opened", a)) == 1
    b = runs.start(origin=origin(), goal="salut, ça va ?")
    assert "task_id" not in runs.update(b, thread_id=thread(), act="new", requested=CHAT)
    c = runs.start(origin=origin(), goal="réponse toute faite")
    assert "task_id" not in runs.update(c, thread_id=thread(), act="new", requested={**CODING, "fast_path": True})
    assert runs.actionable({"task": "general", "level": "L2"}) and not runs.actionable(None)


def test_a_continuation_from_another_session_attaches_to_the_threads_objective():
    th, s1, s2 = thread(), f"{RT}/vm/{uuid.uuid4()}", f"{RT}/telegram/{uuid.uuid4()}"
    a = runs.start(origin=origin(s1), goal="déploie la nouvelle page"); opened = runs.update(a, thread_id=th, act="new",
                                                                                              requested=CODING)
    runs.end(a)
    b = runs.start(origin=origin(s2), goal="continue")                         # another interface, same thread
    out = runs.update(b, thread_id=th, act="continue", requested=CHAT)
    assert out["task"] == "attached" and out["task_id"] == opened["task_id"]
    [t] = runs.tasks_list(session_id=s2.rsplit("/", 1)[-1])                   # found from the other session too
    assert t["task_id"] == opened["task_id"] and t["attempts"] == 2
    assert runs.tasks_list(session_id=s1)[0]["task_id"] == opened["task_id"]
    assert bus("task.updated", b)[0]["payload"]["reason"] == "attached"


def test_the_thread_of_the_sessions_last_run_is_known_at_once():
    """An approval sent seconds after an exchange: Memory has not attached a subject yet, the Run Plane knows."""
    sid = f"s-{uuid.uuid4().hex[:8]}"
    a = runs.start(origin=origin(sid), goal="propose un plan pour ranger les photos")
    runs.update(a, thread_id="subject:photos", act="new", requested=CHAT)       # a plain exchange: no objective
    runs.end(a)
    runs.start(origin=origin(sid), goal="ok vas-y pour la première")        # the engine opens the run, then plans it
    out = runs.objective_candidates("ok vas-y pour la première", session_id=sid)
    assert out["waiting"] == "subject:photos" and out["waiting_age_s"] is not None and out["waiting_age_s"] < 60
    assert runs.objective_candidates("ok vas-y", session_id=f"s-{uuid.uuid4().hex[:8]}")["waiting"] is None


def test_the_subject_of_the_last_run_is_offered_to_the_preflight_even_when_its_words_are_far():
    """« ok vas-y pour la première » shares no word with the subject it answers: the thread of the session's last
    run is a candidate card anyway (2026-11-12: it was missing, the reply went to another subject)."""
    from walter_memory import views
    from walter_memory.db import connection
    key, sid = f"subject:pytest-{uuid.uuid4().hex[:8]}", f"{RT}/vm/{uuid.uuid4()}"
    with connection() as conn:
        conn.execute("insert into views.view (view_key, domain, horizon, title, last_at) values (%s, 'projects', 'medium', "
                     "'Rangement des photos', now())", (key,))
    a = runs.start(origin=origin(sid), goal="propose un plan pour ranger les photos")
    runs.update(a, thread_id=key, act="new", requested=CHAT)
    runs.end(a)
    runs.start(origin=origin(sid), goal="ok vas-y pour la première")
    got = views.subject_candidates("ok vas-y pour la première", sid, embed=lambda texts: [[0.0, 1.0] for _ in texts])
    assert got["waiting"] == key and any(c["id"] == key for c in got["candidates"])


def test_a_degraded_plan_carries_on_an_open_task_but_opens_none():
    """13/11/2026: with the decision model unreachable every plan is degraded — prudent tier, tools — and the Run
    Plane read that prudence as « this is work »: a bare « continue » opened a task under its own words."""
    s = f"{RT}/telegram/{uuid.uuid4()}"
    degraded = {"task": "general", "level": "L3", "require": ["tools"], "degraded": True}
    assert not runs.actionable(degraded) and runs.actionable({k: v for k, v in degraded.items() if k != "degraded"})
    a = runs.start(origin=origin(s), goal="continue là où tu en étais")
    assert "task_id" not in runs.update(a, act="new", requested=degraded)
    runs.end(a, status="ended")
    b = runs.start(origin=origin(s), goal="tâche en deux étapes : écris deux noms de fleurs, puis trie-les")
    opened = runs.update(b, act="new", requested={**CODING, "work": True})
    runs.end(b, status="ended")
    c = runs.start(origin=origin(s), goal="continue")                    # the open task of the conversation goes on
    out = runs.update(c, act="continue", requested=degraded)
    assert (out["task_id"], out["task"]) == (opened["task_id"], "attached")


def test_a_resumption_from_another_interface_carries_on_the_subjects_task():
    """13/11/2026 (live engine): a task opened on Telegram inside a known subject, interrupted, then « reprends la
    tâche … » through the API. A new session has no previous exchange, the act came back « new », and a second
    objective was opened next to the suspended one. The preflight now judges the resumption (`requested.resume`) and
    the subject's card says the task it carries."""
    from walter_memory import views
    from walter_memory.db import connection
    key, s1, s2 = f"subject:pytest-{uuid.uuid4().hex[:8]}", f"{RT}/telegram/{uuid.uuid4()}", f"{RT}/api/{uuid.uuid4()}"
    with connection() as conn:
        conn.execute("insert into views.view (view_key, domain, horizon, title, last_at) values (%s, 'projects', 'medium', "
                     "'Liste des arbres', now())", (key,))
    a = runs.start(origin=origin(s1), goal="tâche en trois étapes : écris trois noms d'arbres, puis trie-les")
    opened = runs.update(a, thread_id=key, act="new", requested={**CODING, "work": True})
    runs.end(a, status="cancelled", outcome={"status": "interrupted", "reason": "engine_restart"})
    got = views.subject_candidates("reprends la tâche des arbres et termine-la", s2,
                                   embed=lambda texts: [[0.0, 1.0] for _ in texts])
    card = next(c for c in got["candidates"] if c["id"] == key)            # the task stands for its thread there
    assert card["kind"] == "task" and card["state"].startswith("tâche suspendue")
    runs.start(origin=origin(s1), goal="reprends la tâche des arbres")       # where the subject itself is a card
    got = views.subject_candidates("reprends la tâche des arbres", s1, embed=lambda texts: [[0.0, 1.0] for _ in texts])
    card = next(c for c in got["candidates"] if c["id"] == key)
    assert card["task"].startswith("tâche suspendue") and "trois noms d'arbres" in card["task"]
    assert [c["id"] for c in got["candidates"]].count(key) == 1
    b = runs.start(origin=origin(s2), goal="reprends la tâche des arbres et termine-la")
    out = runs.update(b, thread_id=key, act="new", requested={**CODING, "work": True, "resume": True})
    assert out == {"task_id": opened["task_id"], "task": "reopened"}
    assert runs.task_get(opened["task_id"])["status"] == "open"
    # without that judgement a new request in the same subject is another piece of work: its own objective
    c = runs.start(origin=origin(s2), goal="ajoute aussi une liste de fleurs")
    other = runs.update(c, thread_id=key, act="new", requested={**CODING, "work": True})
    assert other["task"] == "opened" and other["task_id"] != opened["task_id"]


def test_an_interrupted_run_suspends_its_objective_at_once():
    a = runs.start(origin=origin(), goal="trier les trois fichiers du dossier")
    tid = runs.update(a, act="new", requested=CODING)["task_id"]
    runs.end(a, "cancelled", outcome={"status": "interrupted", "error": {"kind": "engine_restart"}})
    t = runs.task_get(tid)
    assert t["status"] == "suspended" and "interrupted" in t["last_outcome"] and "engine_restart" in t["last_outcome"]
    b = runs.start(origin=origin(), goal="reprends le tri")             # the continuation re-opens it
    assert runs.update(b, thread_id=t["thread_id"], act="continue", requested=CODING)["task_id"] == tid
    assert runs.task_get(tid)["status"] == "open"
    runs.end(a, "cancelled", outcome={"status": "interrupted"})         # a late duplicate never rewinds it
    assert runs.task_get(tid)["status"] == "open"


def test_the_preflights_own_judgement_decides_what_is_a_task():
    assert runs.actionable({"task": "general", "level": "L1", "work": True})        # a plain three-step errand
    assert not runs.actionable({"task": "coding", "level": "L3", "work": False})    # « try again », an opinion
    assert not runs.actionable({"work": True, "fast_path": "trivial"})
    assert runs.actionable(CODING) and not runs.actionable(CHAT)                    # no judgement: the proxy
    a = runs.start(origin=origin(), goal="range mes notes en trois étapes")
    assert runs.update(a, act="new", requested={**CHAT, "work": True})["task"] == "opened"
    assert runs.show(a)["run"]["routing"]["requested"]["work"] is True
    b = runs.start(origin=origin(), goal="essaie encore")
    assert "task_id" not in runs.update(b, act="new", requested={**CODING, "work": False})


def test_an_objective_without_a_subject_is_its_own_thread_and_is_proposed_to_any_session():
    """A new request has no subject yet (subjects are attached after the exchange): its objective is its own thread,
    a candidate of the preflight from another session or interface, and the run that picks it works on it."""
    from walter_memory import views
    s1 = f"{RT}/vm/{uuid.uuid4()}"
    a = runs.start(origin=origin(s1), goal="Range le dossier photos-pytest en trois étapes : inventaire, tri, archive")
    opened = runs.update(a, act="new", requested=CODING)
    tid = opened["task_id"]
    th = "task:" + tid
    assert runs.show(a)["run"]["thread_id"] == th and runs.task_get(tid)["thread_id"] == th
    runs.end(a, status="cancelled", outcome={"status": "interrupted"})
    runs.task_update(tid, status="suspended")

    embed = lambda texts: [[1.0, 0.0] if "photos-pytest" in t else [0.0, 1.0] for t in texts]      # noqa: E731
    other = f"{RT}/vm/{uuid.uuid4()}"                       # another interface, a new session
    got = views.subject_candidates("Reprends le rangement du dossier photos-pytest", other, embed=embed)
    card = next(c for c in got["candidates"] if c["id"] == th)
    assert card["kind"] == "task" and "suspendue" in card["state"] and got["waiting"] is None
    far = views.subject_candidates("Quel temps fait-il demain ?", other, embed=embed)
    assert all(c["id"] != th for c in far["candidates"])   # an unrelated message is not offered the task
    same = views.subject_candidates("ok", s1, embed=embed)  # the session that worked on it: its thread is waiting
    assert same["waiting"] == th and any(c["id"] == th for c in same["candidates"])

    b = runs.start(origin=origin(other), goal="Reprends le rangement du dossier photos-pytest")
    out = runs.update(b, thread_id=th, act="new", requested=CODING)       # whatever the act: the thread is the task
    assert out == {"task_id": tid, "task": "reopened"} and runs.task_get(tid)["status"] == "open"
    assert runs.tasks_list(thread_id=th)[0]["attempts"] == 2

    c = runs.start(origin=origin(other), goal="continue")                 # no thread: the session stands in, and the
    assert runs.update(c, act="continue", requested=CHAT)["task_id"] == tid   # run then carries the task's thread
    assert runs.show(c)["run"]["thread_id"] == th
    runs.task_update(tid, status="done")
    done = views.subject_candidates("Reprends le rangement du dossier photos-pytest", other, embed=embed)
    assert all(x["id"] != th for x in done["candidates"])  # a closed task is no longer a thread to carry on


def test_an_idle_objective_is_suspended_never_lost_and_a_continuation_reopens_it():
    th = thread()
    a = runs.start(origin=origin(), goal="migre la base"); tid = runs.update(a, thread_id=th, act="new",
                                                                            requested=CODING)["task_id"]
    runs.end(a)
    with connect() as c:
        c.execute("update runs.tasks set updated_at = now() - interval '4 days' where task_id = %s", (tid,))
    runs.sweep()
    assert runs.task_get(tid)["status"] == "suspended"
    assert runs.tasks_list(thread_id=th)[0]["status"] == "suspended"          # still listed (active)
    b = runs.start(origin=origin(), goal="on reprend")
    assert runs.update(b, thread_id=th, act="continue")["task"] == "reopened"
    assert runs.task_get(tid)["status"] == "open"
    with connect() as c:                                                      # an objective is never abandoned
        c.execute("update runs.tasks set started_at = now() - interval '3 days' where task_id = %s", (tid,))
    runs.sweep()
    assert runs.task_get(tid)["status"] == "open"


def test_a_correction_reopens_a_done_objective_and_an_old_one_is_not_carried_on():
    th = thread()
    a = runs.start(origin=origin(), goal="écris le rapport"); tid = runs.update(a, thread_id=th, act="new",
                                                                               requested=CODING)["task_id"]
    runs.task_update(tid, status="done")
    b = runs.start(origin=origin(), goal="non, il manque la section 2")
    assert runs.update(b, thread_id=th, act="correct")["task"] == "reopened"
    with connect() as c:
        c.execute("update runs.tasks set updated_at = now() - interval '20 days' where task_id = %s", (tid,))
    d = runs.start(origin=origin(), goal="continue")
    assert "task_id" not in runs.update(d, thread_id=th, act="continue", requested=CHAT)


def test_delegated_work_inherits_the_objective():
    th = thread()
    a = runs.start(origin=origin(), goal="compare trois fournisseurs")
    tid = runs.update(a, thread_id=th, act="new", requested=CODING)["task_id"]
    sub = runs.task_start(a, kind="walter_run", goal="recherche fournisseur A")
    with connect() as c:
        assert str(c.execute("select parent_task_id from runs.tasks where task_id = %s", (sub,)).fetchone()
                   ["parent_task_id"]) == tid
    child = runs.start(origin=origin(channel="machine"), goal="sous-agent", parent_run_id=a)
    assert runs.objective_of_run(child) == tid
    assert "task_id" not in runs.update(child, thread_id=thread(), act="new", requested=CODING) or \
        runs.objective_of_run(child) == tid                                    # a machine run never opens one
    with connect() as c:
        n = c.execute("select count(*) n from runs.tasks where kind = 'objective' and run_id = %s", (child,)).fetchone()["n"]
    assert n == 0


def test_task_update_merges_progress_and_notes_and_closes():
    a = runs.start(origin=origin(), goal="prépare le devis")
    tid = runs.update(a, thread_id=thread(), act="new", requested=CODING)["task_id"]
    runs.task_update(tid, progress={"done": ["gabarit"], "next": ["prix"]}, note="clé <secret:redacted> notée")
    t = runs.task_update(tid, progress={"next": ["envoi"]})
    assert t["progress"]["done"] == ["gabarit"] and t["progress"]["next"] == ["envoi"]
    assert "sk-proj-AbCd" not in json.dumps(t["progress"]["notes"])
    assert runs.task_update(tid, status="nope")["error"].startswith("unknown status")
    done = runs.task_update(tid, status="done", result={"summary": "envoyé", "refs": {"runs": [a]}})
    assert done["status"] == "done"
    with connect() as c:
        assert c.execute("select ended_at from runs.tasks where task_id = %s", (tid,)).fetchone()["ended_at"]


def test_run_outcome_is_stored_masked_and_emitted():
    a = runs.start(origin=origin(), goal="appelle l'API")
    runs.end(a, "failed", outcome={"status": "failed", "steps": 3, "tool_calls": 4, "tool_errors": 2, "extra": "x",
                                   "error": {"kind": "provider_error",
                                             "message": "401 with key <secret:redacted> " + "x" * 900}})
    with connect() as c:
        o = c.execute("select outcome from runs.runs where run_id = %s", (a,)).fetchone()["outcome"]
    assert o["status"] == "failed" and o["tool_errors"] == 2 and "extra" not in o
    assert "sk-proj-AbCd" not in o["error"]["message"] and len(o["error"]["message"]) <= runs.OUTCOME_MESSAGE_MAX
    [ev] = bus("run.ended", a)
    assert ev["payload"]["outcome"] == o and ev["payload"]["status"] == "failed"
    b = runs.start(origin=origin(), goal="sans outcome"); runs.end(b)        # the previous call shape still works
    assert "outcome" not in bus("run.ended", b)[0]["payload"]


# ── gateway ──────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(gateway, "TOKEN", "t-tasks")
    monkeypatch.setenv("WALTER_EPISODES", "off")
    c = TestClient(gateway.app)
    c.headers["Authorization"] = "Bearer t-tasks"
    return c


def test_gateway_task_routes_need_the_token(client):
    for path in ("/v1/tasks/list", "/v1/tasks/update", "/v1/experience"):
        assert client.post(path, json={"task_id": "x"}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_gateway_tasks_list_update_experience_and_run_end_outcome(client):
    sid, th = f"{RT}/vm/{uuid.uuid4()}", thread()
    r = client.post("/v1/runs/start", json={"origin": {**origin(sid), "interface": "telegram", "engine_session": "e-1",
                                                        "request_id": "req-9"}, "goal": "range le dossier"}).json()
    with connect() as c:
        o = c.execute("select origin from runs.runs where run_id = %s", (r["run_id"],)).fetchone()["origin"]
    assert (o["interface"], o["engine_session"], o["request_id"]) == ("telegram", "e-1", "req-9")
    assert client.post("/v1/runs/start", json={"origin": {**origin(), "interface": {"x": 1}}}).status_code == 422
    tid = runs.update(r["run_id"], thread_id=th, act="new", requested=CODING)["task_id"]
    listed = client.post("/v1/tasks/list", json={"thread_id": th}).json()["tasks"]
    assert [t["task_id"] for t in listed] == [tid] and listed[0]["attempts"] == 1
    assert client.post("/v1/tasks/list", json={"session_id": sid, "status": "all", "limit": 3}).json()["tasks"][0]["task_id"] == tid
    up = client.post("/v1/tasks/update", json={"task_id": tid, "progress": {"next": ["trier"]}, "note": "commencé"})
    assert up.status_code == 200 and up.json()["progress"]["next"] == ["trier"]
    assert client.post("/v1/tasks/update", json={"task_id": str(uuid.uuid4())}).status_code == 404
    assert client.post("/v1/tasks/update", json={"task_id": tid, "status": "bogus"}).status_code == 422
    end = client.post("/v1/runs/end", json={"run_id": r["run_id"], "status": "failed",
                                            "outcome": {"status": "failed", "error": {"kind": "tool", "message": "boom"}}})
    assert end.json()["run_id"] == r["run_id"]
    with connect() as c:
        assert c.execute("select outcome from runs.runs where run_id = %s", (r["run_id"],)).fetchone()["outcome"]["error"]["kind"] == "tool"
    items = client.post("/v1/experience", json={"thread_id": th, "limit": 3}).json()["items"]
    assert items == []                                                       # no episode yet (episodes off)


# ── triage: a failed decision is never final ─────────────────────────────────────────────────────────────────────

def _ev(ingested_at):
    return {"event_id": uuid.uuid4(), "event_type": "message.received", "source": "beeper",
            "thread_id": f"pytest-tasks-{uuid.uuid4().hex[:6]}", "occurred_at": ingested_at, "ingested_at": ingested_at,
            "content": "tu viens ce soir ?", "payload": {"chat": {"type": "single", "network": "pytest"}},
            "privacy_class": "cloud_allowed"}


def _row(event_id):
    with connect() as c:
        return c.execute("select * from triage.decisions where event_id = %s", (event_id,)).fetchone()


def test_a_failed_triage_decision_is_not_stored_and_is_retried(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(triage.llm, "decide", boom)
    ev = _ev(datetime.now(timezone.utc))
    out = triage._decide([ev])
    assert out["errors"] == 1 and out["retry_later"] == 1 and _row(ev["event_id"]) is None
    old = _ev(datetime.now(timezone.utc) - timedelta(days=3))              # past the retry window: kept, error noted
    triage._decide([old])
    row = _row(old["event_id"])
    assert row["action"] == "remember" and row["payload"]["error"].startswith("RuntimeError")
    monkeypatch.setattr(triage.llm, "decide", lambda *a, **k: {"model": "m", "answers": {
        "action": {"choice": "notify", "confidence": 0.9}, "urgency": {"choice": "now"},
        "category": {"choice": "personal"}, "needs_reply": {"noul": 0.9}}})
    triage._decide([{**old, "ingested_at": datetime.now(timezone.utc)}], replace_errors=True)   # re-decided
    row = _row(old["event_id"])
    assert row["model_action"] == "notify" and row["payload"].get("error") is None
    assert row["payload"]["previous"]["error"].startswith("RuntimeError")
    triage._decide([{**old, "ingested_at": datetime.now(timezone.utc)}], replace_errors=True)   # a good row stays
    assert _row(old["event_id"])["payload"]["previous"]["error"].startswith("RuntimeError")


def test_before_migration_037_the_previous_behaviour_stands(monkeypatch):
    """Production imports this tree before 037 is applied: no new table or column is touched then."""
    from walter_memory import context, episodes
    monkeypatch.setattr(runs, "has_tasks_schema", lambda conn=None: False)
    a = runs.start(origin=origin(), goal="corrige le bug")
    assert runs.update(a, thread_id=thread(), act="new", requested=CODING) == {}
    runs.end(a, "failed", outcome={"status": "failed", "error": {"kind": "x", "message": "y"}})
    with connect() as c:
        assert c.execute("select outcome from runs.runs where run_id = %s", (a,)).fetchone()["outcome"] is None
    assert episodes.build(a, summarise=False) == {"skipped": "trivial run"}    # the previous significance rule
    assert runs.tasks_list() == [] and episodes.experience(thread_id="t") == [] and runs.suspend_idle() == []
    assert runs.task_update(str(uuid.uuid4()))["error"].startswith("tasks schema")
    zero = {k: 0 for k in context.DEFAULT_BUDGET}
    res = context.get_context("x", budget={**zero, "tasks": 250, "experience": 350}, include_profile=False)
    assert "tasks" not in res["sections"] and "experience" not in res["sections"]


def test_context_degraded_is_open_on_the_bus_with_metadata_only(client):
    ok = client.post("/v1/bus/emit", json={"type": "context.degraded", "source": RT, "subject": "r1",
                                           "payload": {"run_id": "r1", "stage": "preflight", "reason": "timeout"}})
    assert ok.status_code == 200
    bad = client.post("/v1/bus/emit", json={"type": "context.degraded", "source": RT,
                                            "payload": {"run_id": "r1", "message": "texte du propriétaire"}})
    assert bad.status_code == 422
    with connect() as c:
        c.execute("delete from bus.events where source = %s", (RT,))


def test_context_route_honours_zero_budgets_for_the_new_layers(client):
    th = thread()
    a = runs.start(origin=origin(), goal="prépare la migration")
    runs.update(a, thread_id=th, act="new", requested=CODING)
    from walter_memory import context
    zero = {k: 0 for k in context.DEFAULT_BUDGET}
    on = client.post("/v1/context", json={"query": "migration", "budget": {**zero, "tasks": 250}, "thread_id": th,
                                          "include_profile": False}).json()
    assert "tasks" in on["sections"]
    off = client.post("/v1/context", json={"query": "migration", "budget": zero, "thread_id": th,
                                           "include_profile": False}).json()
    assert "tasks" not in off["sections"] and "experience" not in off["sections"]
    assert "tasks" not in off["trace"]["sections"]
    with connect() as c:
        c.execute("delete from system.context_requests where caller = 'unknown' and query_sha = encode(sha256('migration'::bytea), 'hex')")


def test_the_hourly_reconciliation_closes_runs_that_never_ended(monkeypatch):
    """No timer and no lucky start: the pipeline's reconciliation owns the Run Plane's deadlines."""
    from walter_memory import assimilation, episodes
    monkeypatch.setattr(episodes, "pending", lambda *a, **k: [])
    old = runs.start(origin=origin(), goal="jamais terminé")
    fresh = runs.start(origin=origin(), goal="en cours")
    with connect() as c:
        c.execute("update runs.runs set started_at = now() - interval '30 hours' where run_id = %s", (old,))
    out = assimilation.reconcile_runs()
    assert out["abandoned"] >= 1 and out["episodes"] == 0
    with connect() as c:
        status = {str(r["run_id"]): r["status"] for r in c.execute(
            "select run_id, status from runs.runs where run_id::text = any(%s)", ([old, fresh],))}
    assert status == {old: "abandoned", fresh: "open"}
    monkeypatch.setattr(runs, "sweep", lambda: 1 / 0)             # one step failing never stops the others
    assert assimilation.reconcile_runs() == {"abandoned": "error: ZeroDivisionError", "episodes": 0}
