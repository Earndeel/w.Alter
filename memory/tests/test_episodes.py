"""P4: corrections linked to the run they correct; deterministic episode evaluation; parent re-versioned.
Writes pytest runs (origin.runtime = pytest) and removes them; no model call (summarise=False)."""
import pytest

from walter_memory import episodes, runs
from walter_memory.db import connect


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with connect() as c:
        ids = [str(r["run_id"]) for r in c.execute("select run_id from runs.runs where origin->>'runtime' = 'pytest'")]
        if ids:
            c.execute("delete from runs.episodes where run_id::text = any(%s)", (ids,))
            c.execute("delete from bus.events where source = 'runs' and subject = any(%s)", (ids,))
            c.execute("delete from runs.links where run_id::text = any(%s)", (ids,))
            c.execute("delete from runs.tasks where run_id::text = any(%s)", (ids,))
            c.execute("update runs.runs set parent_run_id = null where run_id::text = any(%s)", (ids,))
            c.execute("delete from runs.runs where run_id::text = any(%s)", (ids,))


def origin(sid="pytest/ep"):
    return {"channel": "owner", "runtime": "pytest", "session_id": sid}


def test_a_correction_is_linked_to_the_previous_run_of_its_session():
    a = runs.start(origin=origin(), goal="meilleur café"); runs.end(a)
    b = runs.start(origin=origin(), goal="je préfère la qualité")
    assert runs.update(b, act="correct") == {"parent_run_id": a}
    shown = runs.show(b)["run"]
    assert str(shown["parent_run_id"]) == a and shown["correction"] == {"scope": "run"} and shown["act"] == "correct"
    c = runs.start(origin=origin("pytest/other"), goal="autre chose")
    assert runs.update(c, act="new") == {}                       # a new request links to nothing


def test_trivial_runs_get_no_episode_and_tasks_get_an_evaluation():
    a = runs.start(origin=origin(), goal="bonjour"); runs.end(a)
    assert episodes.build(a, summarise=False) == {"skipped": "trivial run"}
    b = runs.start(origin=origin(), goal="recherche")
    t = runs.task_start(b, kind="walter_run", goal="sous-tâche")
    runs.routing(b, {"model_id": "m", "applied": True}, task_id=t)
    runs.task_end(t, result={"ok": True, "persisted": {"stored": 2, "errors": []}})
    runs.end(b)
    ep = episodes.build(b, summarise=False)
    ev = ep["evaluation"]
    assert ep["version"] == 1 and ev["technical"]["status"] == "ok" and ev["technical"]["tasks"] == 1
    assert ev["functional"]["contract"] == "filled" and ev["satisfaction"] == "unknown"


def test_a_correction_re_versions_the_parent_episode_with_satisfaction_corrected():
    a = runs.start(origin=origin(), goal="recherche")
    t = runs.task_start(a, kind="walter_run"); runs.task_end(t, result={"ok": True}); runs.end(a)
    assert episodes.build(a, summarise=False)["version"] == 1
    b = runs.start(origin=origin(), goal="non, plutôt la qualité"); runs.update(b, act="correct"); runs.end(b)
    out = episodes.build(b, summarise=False)                     # the correction itself is trivial
    assert out["skipped"] == "trivial run" and out["parent"]["version"] == 2
    latest = episodes.latest(a)
    assert latest["reason"] == "child_run" and latest["evaluation"]["satisfaction"] == "corrected"
