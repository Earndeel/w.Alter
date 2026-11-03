"""Working memory (P1.1), test database: pending owner instructions stay verbatim until interpreted; the state is the
same from another runtime on the same subject (it is rebuilt from Memory, not from a model window); audience rules;
the agent's plan without a model; the adaptive trigger; the shadow record."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import events, extract2, generations, pipeline, working
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def setup():
    extract2.set_v1_start(NOW - timedelta(days=1))
    generations.rollback(confirm=True)


def say(source, thread, who, text, at, privacy="cloud_allowed"):
    return events.record_events([{"event_type": "message.sent" if who == "owner" else "message.received",
                                  "source": source, "source_account": "pytest", "source_id": uuid.uuid4().hex,
                                  "thread_id": thread, "occurred_at": at, "content": text,
                                  "privacy_class": privacy}])["event_ids"][0]


def model_from(items):
    def chat(messages, **kw):
        return {"content": json.dumps({"summary": "", "items": items}), "cost_usd": 0, "model": "scripted",
                "usage": {"prompt_tokens": len(messages[0]["content"]) // 4}}
    return chat


def test_pending_stays_verbatim_until_interpreted_then_becomes_knowledge():
    t = f"w-{uuid.uuid4().hex[:8]}"
    say("claude_code", t, "owner", "Ne touche jamais au fichier config.yaml de Hermes, c'est clair ?", NOW - timedelta(minutes=3))
    st = working.state("claude_code", t)
    assert [p["text"] for p in st["pending"]] == ["Ne touche jamais au fichier config.yaml de Hermes, c'est clair ?"]
    assert "mot pour mot" in st["text"] and "config.yaml" in st["text"]
    extract2.process_thread("claude_code", t, force=True, chat=model_from([
        {"kind": "constraint", "text": "Ne jamais modifier config.yaml de Hermes", "msgs": [1],
         "quote": "Ne touche jamais au fichier config.yaml de Hermes"}]))
    st = working.state("claude_code", t)
    assert [p for p in st["pending"] if not p.get("last")] == [] and st["interpreted"]["constraint"][0]["text"] == "Ne jamais modifier config.yaml de Hermes"


def test_an_instruction_with_nothing_durable_leaves_pending_without_loss():
    t = f"e-{uuid.uuid4().hex[:8]}"
    say("codex", t, "owner", "ok merci", NOW - timedelta(minutes=30))
    say("codex", t, "agent", "Avec plaisir.", NOW - timedelta(minutes=29))
    extract2.process_thread("codex", t, force=True, chat=model_from([]))
    assert [p["text"] for p in working.state("codex", t)["pending"]] == ["ok merci"]   # only as the last message, verbatim


def test_same_state_from_another_runtime_on_the_same_subject():
    a, b, key = f"a-{uuid.uuid4().hex[:8]}", f"b-{uuid.uuid4().hex[:8]}", f"pytest-subject-{uuid.uuid4().hex[:6]}"
    say("hermes", a, "owner", "Pour Orion, le budget est plafonné à 500 euros", NOW - timedelta(minutes=10))
    extract2.process_thread("hermes", a, force=True, chat=model_from([
        {"kind": "constraint", "text": "Budget d'Orion plafonné à 500 euros", "msgs": [1],
         "quote": "le budget est plafonné à 500 euros"}]))
    say("hermes", a, "owner", "et livre avant vendredi", NOW - timedelta(minutes=8))           # not interpreted yet
    say("codex", b, "owner", "on reprend Orion ici", NOW - timedelta(minutes=1))
    with connection() as conn:
        conn.execute("insert into views.view (view_key, domain, horizon, title, last_at) values (%s, 'projects', 'medium', 'Orion', now())", (key,))
        for sess, seq in ((f"hermes/vm/{a}", 1), (f"codex/Codex Desktop/{b}", 1)):
            conn.execute("""insert into views.member (session_id, seq, view_key, occurred_at, runtime, attached_by)
                            values (%s, %s, %s, now(), %s, 'pytest')""", (sess, seq, key, sess.split("/")[0]))
    st = working.state("codex", b)                       # the new runtime, after any compression of the old one
    assert "Budget d'Orion plafonné à 500 euros" in st["text"]
    assert "et livre avant vendredi" in st["text"] and "on reprend Orion ici" in st["text"]
    assert not working.state("codex", b, subject=False)["interpreted"]["constraint"]


def test_audience_and_privacy_class():
    t = f"p-{uuid.uuid4().hex[:8]}"
    say("hermes", t, "owner", "mon code de porte est 4521, garde-le pour toi", NOW - timedelta(minutes=5), "local_only")
    say("hermes", t, "owner", "prépare le rendez-vous de demain", NOW - timedelta(minutes=4))
    cloud = working.state("hermes", t)
    assert "4521" not in cloud["text"] and cloud["privacy_class"] == "cloud_allowed"
    local = working.state("hermes", t, audience="owner_local")
    assert "4521" in local["text"] and local["privacy_class"] == "local_only"


def test_pre_v1_messages_are_history_not_pending():
    t = f"old-{uuid.uuid4().hex[:8]}"
    say("codex", t, "owner", "vieille consigne d'avant la V1", NOW - timedelta(days=40))
    extract2.set_v1_start(datetime.now(timezone.utc) + timedelta(seconds=1))
    assert working.state("codex", t)["pending"] == []


def test_agent_plan_is_read_without_a_model():
    t = f"plan-{uuid.uuid4().hex[:8]}"
    sid = f"claude_code/vm/{t}"
    with connection() as conn:
        conn.execute("insert into walter_logs.sessions (session_id, runtime, native_id) values (%s, 'claude_code', %s)", (sid, t))
        for seq, args in enumerate([{"items": [{"content": "Lire", "status": "in_progress"},
                                               {"content": "Écrire", "status": "pending"},
                                               {"content": "Tester", "status": "pending"}]},
                                    {"advance": True}], 1):
            conn.execute("""insert into walter_logs.events (session_id, seq, type, occurred_at, tool, text, privacy_class, source_ref)
                            values (%s, %s, 'tool/call', %s, 'mcp__ccd_turn__update_plan', %s, 'cloud_allowed', %s)""",
                         (sid, seq, NOW - timedelta(minutes=10 - seq), json.dumps(args), f"r{seq}"))
    say("claude_code", t, "owner", "vas-y", NOW - timedelta(minutes=9))
    st = working.state("claude_code", t)
    assert [(i["content"], i["status"]) for i in st["plan"]] == [("Lire", "completed"), ("Écrire", "in_progress"),
                                                                ("Tester", "pending")]
    assert working.session_state(st)["plan"] == "Écrire"


def m(kind, text, minutes_ago):
    at = NOW - timedelta(minutes=minutes_ago)
    return {"event_type": "message.sent" if kind == "o" else "message.received", "content": text,
            "occurred_at": at, "ingested_at": at, "privacy_class": "cloud_allowed"}


@pytest.mark.parametrize("msgs,due,reason", [
    ([m("o", "on garde Postgres finalement", 2), m("a", "Noté.", 1)], True, "marker"),
    ([m("o", "x" * 700, 2), m("a", "Je lis.", 1)], True, "long"),
    ([m("o", "et le reste ?", 2), m("a", "Voici.", 1)], False, None),
    ([m("o", "on garde Postgres finalement", 1)], False, None),                       # turn still open
    ([m("o", "a ?", 4), m("a", "b", 3.5), m("o", "c ?", 3), m("a", "d", 2.5), m("o", "e ?", 2), m("a", "f", 1)], True, "turns"),
    ([m("o", "et le reste ?", 7), m("a", "Voici.", 6)], True, "quiet"),
    ([m("o", "tu peux faire un jeton api pour hostinger", 2), m("a", "C'est fait.", 1)], True, "directive"),
    ([m("o", "pourquoi ça a expiré ?", 2), m("a", "Parce que…", 1)], False, None),
])
def test_adaptive_trigger(msgs, due, reason):
    segs, tail, why = extract2.adaptive_due(msgs, NOW)
    assert bool(segs) == due and why == reason


def test_shadow_records_state_and_decision_without_injecting():
    t = f"sh-{uuid.uuid4().hex[:8]}"
    say("claude_code", t, "owner", "désormais réponds toujours en français", NOW - timedelta(minutes=2))
    say("claude_code", t, "agent", "Entendu.", NOW - timedelta(minutes=1))
    assert pipeline.shadow_working(limit=200) >= 1
    with connection() as conn:
        r = conn.execute("select * from extraction.working_shadow where thread_id = %s", (t,)).fetchone()
    assert r["pending"] == 1 and r["would_call"] and r["reason"] == "marker" and not r["live_due"]
    assert "désormais réponds toujours en français" in r["state"]["pending"]
    with connection() as conn:   # shadow: nothing was extracted
        assert conn.execute("select count(*) n from extraction.covered c join core.events e on e.event_id = c.event_id "
                            "where e.thread_id = %s", (t,)).fetchone()["n"] == 0
