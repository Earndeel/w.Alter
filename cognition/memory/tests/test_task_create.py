"""A created task (E2E 20/11, owner: « Mets une tâche pour que je le relance le 10 décembre et prépare une réponse
sympa. Ne lui envoie rien. »): one objective of the Run Plane with a person, a due date, a source, a draft that is
never sent, and a reminder fired once at its date by the existing scheduler (processing.queue, assimilation) —
delivered to the owner only from his own channel, `dry` from a test run. Throwaway DB only."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import assimilation, runs
from walter_memory.db import connect

BY = "pytest-create"


def _cleanup():
    with connect() as c:
        rows = c.execute("select task_id::text t, run_id::text r from runs.tasks where spec->>'by' = %s", (BY,)).fetchall()
        tids, rids = [r["t"] for r in rows], list({r["r"] for r in rows})
        rids += [str(r["run_id"]) for r in c.execute("select run_id from runs.runs where origin->>'by' = %s "
                                                     "or origin->>'runtime' = %s", (BY, BY))]
        c.execute("delete from processing.queue where processor = %s and key = any(%s)", (runs.REMINDER, tids))
        c.execute("delete from bus.events where source = 'runs' and subject = any(%s)", (rids,))
        c.execute("delete from runs.task_runs where task_id::text = any(%s) or run_id::text = any(%s)", (tids, rids))
        c.execute("delete from runs.tasks where task_id::text = any(%s) or run_id::text = any(%s)", (tids, rids))
        c.execute("delete from runs.links where run_id::text = any(%s)", (rids,))
        c.execute("delete from runs.runs where run_id::text = any(%s)", (rids,))


@pytest.fixture(autouse=True)
def cleanup():
    _cleanup()
    yield
    _cleanup()


def person(name=None):
    name = name or f"Testeur {uuid.uuid4().hex[:6]}"
    with connect() as c:
        return c.execute("""insert into core.entities (entity_type, canonical_name, aliases) values ('person', %s, %s)
                            returning entity_id::text""", (name, [name.lower()])).fetchone()["entity_id"], name


def a_test_run(channel="test"):
    return runs.start(origin={"channel": channel, "runtime": BY, "session_id": f"{BY}/{uuid.uuid4()}"},
                      goal="mets une tâche pour que je le relance")


def queued(tid):
    with connect() as c:
        return c.execute("select due_at from processing.queue where processor = %s and key = %s",
                         (runs.REMINDER, tid)).fetchone()


def test_a_task_with_a_person_a_date_and_a_draft_is_created_read_back_and_never_duplicated():
    eid, name = person()
    rid = a_test_run()
    remind = (datetime.now(timezone.utc) + timedelta(days=20)).replace(microsecond=0)
    kw = dict(entity_id=eid, due_at="2026-12-10", remind_at=remind.isoformat(), run_id=rid, by=BY,
              source={"kind": "conversation", "thread": "e2e"}, draft="Salut ! Tiens-moi au courant pour le 12.")
    with connect() as c:
        sent0 = c.execute("select count(*) n from core.events where event_type = 'message.sent'").fetchone()["n"]
    r = runs.task_create(f"Relancer {name} au sujet du café du 12 décembre", **kw)
    assert r["created"] and r["verified"] and r["sent"] is False and r["channel"] == "test"
    t = r["task"]
    assert t["status"] == "open" and t["person"] == {"entity_id": eid, "name": name} and t["due_at"] == "2026-12-10"
    assert t["remind_at"] == remind.isoformat() and t["draft"]["sent"] is False and "Tiens-moi" in t["draft"]["text"]
    assert t["source"]["kind"] == "conversation"
    assert runs.task_get(t["task_id"])["person"]["entity_id"] == eid                       # found again by re-reading
    q = queued(t["task_id"])
    assert q and abs((q["due_at"] - remind).total_seconds()) < 1                          # the scheduler holds its date
    # a test run's task never reaches the owner's list; its own channel shows it
    assert t["task_id"] not in [x["task_id"] for x in runs.tasks_list(channels=["owner"], limit=100)]
    assert t["task_id"] in [x["task_id"] for x in runs.tasks_list(channels=["test"], limit=100)]
    # replay: the same task, no second one, the date still scheduled once
    again = runs.task_create(f"Relancer {name} au sujet du café du 12 décembre", **kw)
    assert not again["created"] and again["task"]["task_id"] == t["task_id"] and again["verified"]
    with connect() as c:
        n = c.execute("select count(*) n from runs.tasks where spec->'person'->>'entity_id' = %s", (eid,)).fetchone()["n"]
        sent1 = c.execute("select count(*) n from core.events where event_type = 'message.sent'").fetchone()["n"]
    assert n == 1 and sent1 == sent0                                                        # the draft was not sent


def test_the_reminder_fires_once_at_its_date_and_a_test_runs_stays_dry(monkeypatch):
    eid, name = person()
    remind = datetime.now(timezone.utc) + timedelta(hours=2)
    r = runs.task_create(f"Relancer {name}", entity_id=eid, remind_at=remind.isoformat(), run_id=a_test_run(), by=BY)
    tid = r["task"]["task_id"]
    sent = []
    monkeypatch.setattr(runs, "_telegram", lambda text: sent.append(text) or True)
    assert runs.remind(tid)["skipped"] == "not yet" and queued(tid)                         # early: due again at its date
    later = remind + timedelta(minutes=1)
    monkeypatch.setattr(runs, "now", lambda: later)
    out = assimilation.work(now=later)                                                       # the real scheduler path
    assert out.get(runs.REMINDER, {}).get("changed") == 1 and not queued(tid)
    rem = runs.task_get(tid)["reminder"]
    assert rem["delivery"] == "dry" and rem["delivered"] is False and not sent              # test channel: nothing sent
    assert runs.remind(tid)["skipped"] == "already fired"
    with connect() as c:
        ev = c.execute("select count(*) n from bus.events where type = 'task.reminder' and payload->>'task_id' = %s",
                       (tid,)).fetchone()["n"]
    assert ev == 1


def test_an_owner_task_reminds_the_owner_once_and_a_closed_one_never(monkeypatch):
    eid, name = person()
    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    r = runs.task_create(f"Relancer {name}", entity_id=eid, remind_at=soon.isoformat(), channel="owner", by=BY)
    assert r["channel"] == "owner" and r["reminder"]["delivery"] == "owner"
    sent = []
    monkeypatch.setattr(runs, "_telegram", lambda text: sent.append(text) or True)
    monkeypatch.setattr(runs, "now", lambda: soon + timedelta(seconds=30))
    assert runs.remind(r["task"]["task_id"])["delivered"] is True
    assert len(sent) == 1 and name in sent[0] and "Rappel" in sent[0]
    assert runs.remind(r["task"]["task_id"])["skipped"] == "already fired" and len(sent) == 1
    # a failed delivery is retried, not lost; a done task is not reminded
    r2 = runs.task_create(f"Appeler {name}", entity_id=eid, remind_at=soon.isoformat(), channel="owner", by=BY)
    monkeypatch.setattr(runs, "_telegram", lambda text: False)
    with pytest.raises(RuntimeError):
        runs.remind(r2["task"]["task_id"])
    assert "reminder" not in runs.task_get(r2["task"]["task_id"])
    runs.task_update(r2["task"]["task_id"], status="done", by=BY)
    assert runs.remind(r2["task"]["task_id"])["skipped"] == "task done"


def test_a_person_is_never_guessed_and_a_reminder_needs_its_zone():
    _, name = person("Homonyme Pytest")
    person("Homonyme Pytest")
    amb = runs.task_create("Relancer Homonyme Pytest", entity_name=name, by=BY)
    assert amb["error"] == "ambiguous person" and len(amb["candidates"]) == 2
    assert runs.task_create("Relancer", entity_name="Personne Inconnue Pytest", by=BY)["error"] == "unknown person"
    assert "time zone" in runs.task_create("Relancer", remind_at="2026-12-10T09:00:00", by=BY)["error"]
    assert "past" in runs.task_create("Relancer", remind_at="2020-01-01T09:00:00+00:00", by=BY)["error"]
    with connect() as c:
        c.execute("delete from core.entities where canonical_name = 'Homonyme Pytest'")


def test_a_dated_task_is_not_suspended_as_idle_and_a_lost_reminder_is_queued_again():
    eid, name = person()
    remind = datetime.now(timezone.utc) + timedelta(days=20)
    r = runs.task_create(f"Relancer {name}", entity_id=eid, due_at="2026-12-10", remind_at=remind.isoformat(),
                         run_id=a_test_run(), by=BY)
    tid = r["task"]["task_id"]
    with connect() as c:
        c.execute("update runs.tasks set updated_at = now() - interval '10 days' where task_id::text = %s", (tid,))
        c.execute("delete from processing.queue where processor = %s and key = %s", (runs.REMINDER, tid))
    assert tid not in runs.suspend_idle() and runs.task_get(tid)["status"] == "open"
    assert runs.reminders_missed() >= 1 and queued(tid)
    # moving the reminder earlier reschedules it (not only later)
    earlier = remind - timedelta(days=10)
    runs.task_update(tid, remind_at=earlier.isoformat(), by=BY)
    assert abs((queued(tid)["due_at"] - earlier).total_seconds()) < 1
