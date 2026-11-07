"""Extraction v2 end to end on the test database, with a scripted model (no network):
bus → dirty thread → segment → validated items; multi-runtime; long session; late event; duplicates; strict
provenance; supersession; local_only never sent; noise without calls; retries and dead letters; pre-V1 isolation."""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import bus, events, extract2, read_policy
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    from walter_memory import search
    monkeypatch.setattr(search, "embed", lambda texts: (_ for _ in ()).throw(RuntimeError("no embedder in tests")))
    extract2.set_v1_start(NOW - timedelta(days=1))
    yield


class Model:
    """Scripted model: `answer(lines)` gets the numbered transcript lines and returns the JSON payload."""
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, messages, **kw):
        prompt = messages[0]["content"]
        self.calls.append({"prompt": prompt, **kw})
        part = prompt.split("Messages à analyser (numérotés, seuls citables) :", 1)[1].split("\n\nRends un JSON", 1)[0]
        lines = [l for l in part.strip().splitlines() if re.match(r"^\d+\. \[", l)]
        known = re.findall(r"^(K\d+)\. \[[^\]]+\] (.*)$", prompt, re.M)
        return {"content": json.dumps(self.answer(lines, dict(known))), "cost_usd": 0.001, "model": "scripted",
                "usage": {"prompt_tokens": len(prompt) // 4}}


def thread():
    return f"t-{uuid.uuid4().hex[:10]}"


def say(source, thread_id, who, text, *, at=None, privacy="cloud_allowed", sid=None, **payload):
    return events.record_events([{
        "event_type": "message.sent" if who == "owner" else "message.received", "source": source,
        "source_account": "pytest", "source_id": sid or uuid.uuid4().hex, "thread_id": thread_id,
        "occurred_at": at or NOW - timedelta(hours=1), "content": text, "privacy_class": privacy,
        "payload": payload}])["event_ids"]


def feed_bus():
    c = bus.Consumer("memory.extract-pytest", ["memory.event"], batch=500)
    return c.drain_batch(extract2.on_bus_events)


def items(thread_id, status=("derived",)):
    with connection() as conn:
        return conn.execute("""select item_id::text, kind, content, status, attributes, source_event_ids, privacy_class
                               from core.derived_items where derived_by = 'l3.extract' and source_refs->>'thread' = %s
                                 and kind <> 'summary' and status = any(%s) order by created_at""",
                            (thread_id, list(status))).fetchall()


def decision(lines, known):
    out = []
    for i, l in enumerate(lines, 1):
        m = re.search(r"\[Monsieur[^\]]*\] (on garde (\w+))", l)
        if m:
            out.append({"kind": "decision", "text": f"Monsieur a décidé de garder {m.group(2)} pour le projet",
                        "subject": "project:demo", "state": "decided", "msgs": [i], "quote": m.group(1) + " pour le projet"})
    return {"summary": "Choix d'outil.", "items": out}


def test_message_to_knowledge_through_the_bus_for_every_runtime():
    model = Model(decision)
    threads = {src: thread() for src in ("hermes", "claude_code", "codex", "dsh")}
    for src, t in threads.items():
        say(src, t, "owner", f"on garde Postgres{src.replace('_', '')} pour le projet, c'est décidé")
        say(src, t, "agent", "Entendu, je note ce choix.")
    assert feed_bus() >= 8
    with connection() as conn:
        dirty = conn.execute("select source from extraction.threads where thread_id = any(%s) and status = 'dirty'",
                             (list(threads.values()),)).fetchall()
    assert {r["source"] for r in dirty} == set(threads)
    for _ in range(3):
        extract2.tick(limit=50, workers=2, chat=model)
    for src, t in threads.items():
        got = items(t)
        assert len(got) == 1 and got[0]["kind"] == "decision", (src, got)
        assert got[0]["attributes"]["state"] == "decided" and got[0]["attributes"]["epistemic"] == "owner_stated"
        assert len(got[0]["source_event_ids"]) == 1      # exactly the cited message, not the whole segment
    with connection() as conn:   # readable by the canonical read boundary (what Context uses)
        row = {"kind": "derived", "ref_id": got[0]["item_id"], "privacy_class": "cloud_allowed", "text": got[0]["content"]}
        assert read_policy.canonical_allowed(conn, row)


def test_a_long_session_gets_new_segments_and_old_ones_are_not_redone():
    model = Model(decision)
    t = thread()
    say("claude_code", t, "owner", "on garde Redis pour le projet", at=NOW - timedelta(hours=3))
    extract2.enqueue(thread=t)
    extract2.process_thread("claude_code", t, chat=model)
    assert len(model.calls) == 1 and len(items(t)) == 1
    say("claude_code", t, "owner", "on garde Kafka pour le projet aussi", at=NOW - timedelta(hours=2))
    extract2.process_thread("claude_code", t, chat=model)
    assert len(model.calls) == 2
    assert "Kafka" in model.calls[1]["prompt"].split("seuls citables")[1] and \
           "Redis" not in model.calls[1]["prompt"].split("seuls citables")[1]       # only the new messages
    assert "Redis" in model.calls[1]["prompt"].split("seuls citables")[0]            # the known item is shown (K)
    assert len(items(t)) == 2
    extract2.process_thread("claude_code", t, chat=model)
    assert len(model.calls) == 2                                                      # nothing left: no call


def test_an_active_thread_waits_unless_full_or_too_old():
    t = thread()
    say("codex", t, "owner", "on garde Nginx pour le projet", at=NOW)   # just ingested: the thread is active
    model = Model(decision)
    r = extract2.process_thread("codex", t, chat=model)
    assert r["waiting"] == 1 and not model.calls
    later = NOW + extract2.IDLE + timedelta(minutes=1)
    extract2.process_thread("codex", t, chat=model, now=later)
    assert len(model.calls) == 1


def test_a_late_older_event_is_still_processed():
    model = Model(decision)
    t = thread()
    say("hermes", t, "owner", "on garde Caddy pour le projet", at=NOW - timedelta(hours=2))
    extract2.process_thread("hermes", t, chat=model)
    say("hermes", t, "owner", "on garde Traefik pour le projet", at=NOW - timedelta(hours=5))   # arrives late, older
    extract2.process_thread("hermes", t, chat=model)
    assert {i["content"].split()[-4] for i in items(t)} == {"Caddy", "Traefik"}


def test_duplicate_events_and_restated_knowledge_create_no_duplicates():
    t = thread()
    sid = uuid.uuid4().hex
    say("codex", t, "owner", "on garde Ansible pour le projet", sid=sid)
    say("codex", t, "owner", "on garde Ansible pour le projet", sid=sid)      # same source id: one event
    with connection() as conn:
        assert conn.execute("select count(*) n from core.events where thread_id = %s", (t,)).fetchone()["n"] == 1
    extract2.process_thread("codex", t, chat=Model(decision))
    say("codex", t, "owner", "je confirme, on garde Ansible pour le projet", at=NOW - timedelta(minutes=50))

    def restate(lines, known):
        k = next(k for k, v in known.items() if "Ansible" in v)
        return {"items": [{"kind": "decision", "text": "Monsieur garde Ansible", "msgs": [1],
                           "quote": "on garde Ansible pour le projet", "same_as": k, "state": "decided"}]}
    extract2.process_thread("codex", t, chat=Model(restate))
    got = items(t)
    assert len(got) == 1 and len(got[0]["source_event_ids"]) == 2    # one item, two pieces of evidence


@pytest.mark.parametrize("bad,reason", [
    ({"msgs": [], "quote": "on garde Vault pour le projet"}, "invalid_citation"),
    ({"msgs": [7], "quote": "on garde Vault pour le projet"}, "invalid_citation"),
    ({"msgs": [1], "quote": "une phrase que personne n'a jamais écrite ici"}, "quote_not_found"),
    ({"msgs": [2], "quote": "Je propose plutôt Consul"}, "no_owner_evidence"),
])
def test_items_with_invalid_provenance_are_quarantined_not_stored(bad, reason):
    t = thread()
    say("dsh", t, "owner", "on garde Vault pour le projet", at=NOW - timedelta(hours=2))
    say("dsh", t, "agent", "Je propose plutôt Consul pour les secrets.", at=NOW - timedelta(hours=2) + timedelta(seconds=5))
    model = Model(lambda lines, known: {"items": [{"kind": "decision", "text": "Décision sur les secrets", **bad}]})
    extract2.process_thread("dsh", t, chat=model)
    assert items(t) == []
    with connection() as conn:
        seg = conn.execute("select status, rejected from extraction.segments where thread_id = %s and status = 'extracted' "
                           "or (thread_id = %s and status = 'empty')", (t, t)).fetchone()
    assert seg["rejected"][0]["reason"] == reason


def test_a_correction_supersedes_and_context_reads_only_the_current_version():
    t = thread()
    say("hermes", t, "owner", "on garde MySQL pour le projet", at=NOW - timedelta(hours=4))
    extract2.process_thread("hermes", t, chat=Model(decision))
    old = items(t)[0]
    say("hermes", t, "owner", "non finalement on passe à Postgres, MySQL est abandonné", at=NOW - timedelta(hours=3))

    def correct(lines, known):
        k = next(k for k, v in known.items() if "MySQL" in v)
        return {"items": [{"kind": "decision", "text": "Monsieur passe à Postgres au lieu de MySQL", "state": "decided",
                           "msgs": [1], "quote": "finalement on passe à Postgres", "supersedes": [k]}]}
    extract2.process_thread("hermes", t, chat=Model(correct))
    with connection() as conn:
        o = conn.execute("select status, valid_to, attributes from core.derived_items where item_id = %s",
                         (old["item_id"],)).fetchone()
        assert o["status"] == "superseded" and o["valid_to"] is not None and o["attributes"]["superseded_by"]
        rows = [{"kind": "derived", "ref_id": i["item_id"], "privacy_class": "cloud_allowed", "text": i["content"]}
                for i in items(t, ("derived", "superseded"))]
        current = read_policy.canonical_filter(conn, rows)
    assert [r["text"] for r in current] == ["Monsieur passe à Postgres au lieu de MySQL"]


def test_an_agent_cannot_supersede_the_owner_it_only_contests():
    t = thread()
    say("codex", t, "owner", "on garde Docker pour le projet", at=NOW - timedelta(hours=4))
    extract2.process_thread("codex", t, chat=Model(decision))
    say("codex", t, "owner", "où en est le déploiement ?", at=NOW - timedelta(hours=3))
    say("codex", t, "agent", "En fait Docker n'est plus utilisé, tout tourne sous systemd.",
        at=NOW - timedelta(hours=3) + timedelta(seconds=5))

    def agent_claims(lines, known):
        k = next(k for k, v in known.items() if "Docker" in v)
        return {"items": [{"kind": "fact", "text": "Tout tourne sous systemd", "msgs": [2],
                           "quote": "tout tourne sous systemd", "supersedes": [k]}]}
    extract2.process_thread("codex", t, chat=Model(agent_claims))
    got = {i["kind"]: i for i in items(t)}
    assert got["decision"]["status"] == "derived" and got["decision"]["attributes"]["contested"] is True
    assert got["fact"]["attributes"]["epistemic"] == "agent_reported"


def test_local_only_never_reaches_a_model_and_is_not_retried_forever():
    t = thread()
    say("hermes", t, "owner", "on garde SECRETPROJECT pour le projet", privacy="local_only", at=NOW - timedelta(hours=2))
    say("hermes", t, "owner", "on garde Grafana pour le projet", at=NOW - timedelta(hours=2) + timedelta(seconds=1))
    model = Model(decision)
    extract2.process_thread("hermes", t, chat=model)
    sent = " ".join(c["prompt"] for c in model.calls)
    assert "SECRETPROJECT" not in sent and all(c["privacy_class"] == "cloud_allowed" for c in model.calls)
    with connection() as conn:
        st = [r["status"] for r in conn.execute("select status from extraction.segments where thread_id = %s", (t,))]
    assert "local_only_unavailable" in st
    n = len(model.calls)
    extract2.process_thread("hermes", t, chat=model)
    assert len(model.calls) == n                      # nothing pending: never re-read


def test_noise_is_covered_without_a_model_call():
    t = thread()
    say("codex", t, "owner", "The following is the Codex agent history whose request action you are assessing...",
        at=NOW - timedelta(hours=2))
    say("codex", t, "agent", '{"risk_level":"low","outcome":"allow"}', model="codex-auto-review",
        at=NOW - timedelta(hours=2) + timedelta(seconds=1))
    model = Model(decision)
    r = extract2.process_thread("codex", t, chat=model)
    assert r["filtered"] == 2 and not model.calls


def test_failures_retry_with_backoff_then_dead_letter_then_replay():
    t = thread()
    say("claude_code", t, "owner", "on garde Loki pour le projet", at=NOW - timedelta(hours=2))
    extract2.enqueue(thread=t)

    def broken(messages, **kw):
        raise ConnectionError("router down")
    with connection() as conn:
        conn.execute("update extraction.threads set last_event_at = '1970-01-01' where thread_id = %s", (t,))
    extract2.tick(limit=1, chat=broken)
    with connection() as conn:
        th = conn.execute("select status, attempts, retry_after > now() later from extraction.threads where thread_id = %s",
                          (t,)).fetchone()
    assert th["status"] == "dirty" and th["attempts"] == 1 and th["later"]
    for _ in range(extract2.MAX_ATTEMPTS):
        with connection() as conn:
            conn.execute("update extraction.threads set retry_after = null, last_event_at = '1970-01-01' "
                         "where thread_id = %s", (t,))
        extract2.tick(limit=1, chat=broken)
    with connection() as conn:
        assert conn.execute("select status from extraction.segments where thread_id = %s", (t,)).fetchone()["status"] == "failed"
    assert extract2.replay(thread=t) == 1
    with connection() as conn:
        conn.execute("update extraction.threads set last_event_at = '1970-01-01' where thread_id = %s", (t,))
    extract2.tick(limit=1, chat=Model(decision))
    assert len(items(t)) == 1


def test_pre_v1_history_is_never_swept_but_can_be_enqueued_explicitly():
    t = thread()
    say("codex", t, "owner", "on garde Elastic pour le projet", at=NOW - timedelta(days=30))
    extract2.set_v1_start(datetime.now(timezone.utc) + timedelta(seconds=1))     # the event above is now pre-V1
    model = Model(decision)
    extract2.reconcile()
    with connection() as conn:
        assert conn.execute("select count(*) n from extraction.threads where thread_id = %s", (t,)).fetchone()["n"] == 0
    extract2.process_thread("codex", t, chat=model)
    assert not model.calls
    extract2.enqueue(thread=t)                          # explicit, targeted catch-up
    extract2.process_thread("codex", t, chat=model)
    assert len(model.calls) == 1 and len(items(t)) == 1


def test_reconcile_finds_threads_the_bus_did_not_report():
    t = thread()
    say("dsh", t, "owner", "on garde Mimir pour le projet", at=NOW - timedelta(hours=2))
    with connection() as conn:   # as if the bus notification had been lost
        conn.execute("delete from extraction.threads where thread_id = %s", (t,))
    r = extract2.reconcile()
    assert r["threads_marked"] >= 1
    with connection() as conn:
        assert conn.execute("select status from extraction.threads where thread_id = %s", (t,)).fetchone()["status"] == "dirty"
        assert conn.execute("select count(*) n from ingestion.reconciliation_runs where connector = 'extraction'").fetchone()["n"] >= 1


def test_many_telemetry_events_make_no_model_call():
    # GPS-like volume: not a runtime conversation → never a thread for the extractor
    model = Model(decision)
    events.record_events([{"event_type": "note.recorded", "source": "walter", "source_account": "pytest-gps",
                           "source_id": f"gps-{uuid.uuid4().hex}", "occurred_at": NOW, "content": f"lat {i}",
                           "privacy_class": "cloud_allowed"} for i in range(300)])
    feed_bus()
    with connection() as conn:   # not a runtime conversation: no thread to extract, so no model call can follow
        assert conn.execute("select count(*) n from extraction.threads where source not in "
                            "('hermes','claude_code','codex','dsh')").fetchone()["n"] == 0
