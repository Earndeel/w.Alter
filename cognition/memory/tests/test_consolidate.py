"""P1.2 on the test database: views rebuilt from current knowledge (no carry-over), supersession and expiry of task
rules, targeted invalidation, privacy from creation (database-enforced), shadow-only serving, reconsolidation
proposals; P1.1 follow-ups: stages of an intention, read-but-uncited owner messages kept verbatim, budgeted state."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from walter_memory import consolidate, events, extract2, generations, views, working
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def setup():
    extract2.set_v1_start(NOW - timedelta(days=30))
    generations.rollback(confirm=True)


def say(source, thread, who, text, at, privacy="cloud_allowed"):
    return events.record_events([{"event_type": "message.sent" if who == "owner" else "message.received",
                                  "source": source, "source_account": "pytest", "source_id": uuid.uuid4().hex,
                                  "thread_id": thread, "occurred_at": at, "content": text,
                                  "privacy_class": privacy}])["event_ids"][0]


def extract(source, thread, items):
    def chat(messages, **kw):
        known = dict(__import__("re").findall(r"^(K\d+)\. \[[^\]]+\] (.*)$", messages[0]["content"], __import__("re").M))
        out = []
        for it in items:
            it = dict(it)
            if "supersedes_text" in it:
                needle = it.pop("supersedes_text")
                it["supersedes"] = [k for k, v in known.items() if needle in v]
            out.append(it)
        return {"content": json.dumps({"summary": "", "items": out}), "cost_usd": 0, "model": "scripted"}
    return extract2.process_thread(source, thread, force=True, chat=chat)


def subject_with(*threads):
    key = f"pytest-subj-{uuid.uuid4().hex[:6]}"
    with connection() as conn:
        conn.execute("insert into views.view (view_key, domain, horizon, title, last_at) values (%s, 'projects', 'medium', %s, now())",
                     (key, f"Projet {key[-6:]}"))
        for k, (source, thread) in enumerate(threads):
            conn.execute("""insert into views.member (session_id, seq, view_key, occurred_at, runtime, attached_by)
                            values (%s, %s, %s, now(), %s, 'pytest')""", (f"{source}/vm/{thread}", k, key, source))
    return key


def read(key, depth="overview", **q):
    return views.read({"depth": depth, "key": key, "shadow": True, "max_tokens": 6000, **q})


def test_views_are_rebuilt_from_current_knowledge_not_from_the_previous_card():
    t = f"c-{uuid.uuid4().hex[:8]}"
    say("claude_code", t, "owner", "Pour Zéphyr on garde MySQL, et ne jamais toucher à la prod le vendredi", NOW - timedelta(hours=5))
    extract("claude_code", t, [
        {"kind": "decision", "text": "Zéphyr utilise MySQL", "stage": "decided", "msgs": [1], "quote": "Pour Zéphyr on garde MySQL"},
        {"kind": "constraint", "text": "Ne jamais toucher à la prod le vendredi", "msgs": [1], "quote": "ne jamais toucher à la prod le vendredi"}])
    s = subject_with(("claude_code", t))
    first = consolidate.build_subject(s)
    assert first["cloud"]["rebuilt"] and "Zéphyr utilise MySQL" in read(consolidate.key_for(s))["content"]
    assert consolidate.build_subject(s)["cloud"]["rebuilt"] is False                 # nothing changed: no rebuild
    say("claude_code", t, "owner", "finalement Zéphyr passe à Postgres", NOW - timedelta(hours=2))
    extract("claude_code", t, [{"kind": "decision", "text": "Zéphyr passe à Postgres", "stage": "decided", "msgs": [1],
                                "quote": "finalement Zéphyr passe à Postgres", "supersedes_text": "MySQL"}])
    with connection() as conn:   # the extraction invalidated the view (targeted)
        assert conn.execute("""select stale_since from views.version where view_key = %s and depth = 'overview'
                               order by version desc limit 1""", (consolidate.key_for(s),)).fetchone()["stale_since"]
    assert consolidate.build_subject(s)["cloud"]["rebuilt"]
    ov, syn = read(consolidate.key_for(s))["content"], read(consolidate.key_for(s), "synthesis")["content"]
    assert "Postgres" in ov and "MySQL" not in ov and "vendredi" in ov                 # old rule kept, old choice gone
    assert "MySQL" in syn and "remplacé" in syn                                       # history shows the change
    with connection() as conn:   # same lineage across the replacement
        ln = conn.execute("""select count(distinct lineage_id) n from core.derived_items where kind = 'decision'
                             and source_refs->>'thread' = %s""", (t,)).fetchone()["n"]
    assert ln == 1


def test_task_rules_expire_when_the_work_stops():
    t = f"x-{uuid.uuid4().hex[:8]}"
    say("codex", t, "owner", "attends mon accord avant de lancer la migration", NOW - timedelta(days=10))
    extract("codex", t, [{"kind": "constraint", "text": "Attendre l'accord de Monsieur avant la migration", "scope": "task",
                          "msgs": [1], "quote": "attends mon accord avant de lancer la migration"},
                         {"kind": "constraint", "text": "Garder une sauvegarde avant toute migration", "scope": "durable",
                          "msgs": [1], "quote": "avant de lancer la migration"}])
    s = subject_with(("codex", t))
    consolidate.build_subject(s)
    assert "Attendre l'accord" in read(consolidate.key_for(s))["content"]
    r = consolidate.expire()
    assert r["expired_task_rules"] >= 1 and r["views_invalidated"] >= 1
    consolidate.build_subject(s)
    ov, syn = read(consolidate.key_for(s))["content"], read(consolidate.key_for(s), "synthesis")["content"]
    assert "Attendre l'accord" not in ov and "Garder une sauvegarde" in ov and "expiré" in syn


def test_privacy_from_creation_is_enforced_by_the_database():
    t = f"p-{uuid.uuid4().hex[:8]}"
    say("hermes", t, "owner", "le code du portail est 4521 et on garde Caddy", NOW - timedelta(hours=3), "local_only")
    say("hermes", t, "owner", "on garde Nginx pour le site public", NOW - timedelta(hours=2))
    with connection() as conn:   # local_only knowledge as an authorised local extractor would write it
        conn.execute("""insert into core.derived_items (kind, content, status, derived_by, generation, privacy_class, stage,
                            epistemic, scope, source_refs, valid_from)
                        values ('constraint', 'Le code du portail est 4521', 'derived', 'l3.extract', 'g1', 'local_only',
                                'stated', 'stated_owner', 'durable', %s, now())""",
                     (json.dumps({"thread": t, "source": "hermes", "ref": f"loc-{t}"}),))
    extract("hermes", t, [{"kind": "decision", "text": "Le site public utilise Nginx", "stage": "decided", "msgs": [1],
                           "quote": "on garde Nginx pour le site public"}])
    s = subject_with(("hermes", t))
    r = consolidate.build_subject(s)
    assert r["cloud"]["privacy_class"] == "cloud_allowed" and r["local"]["privacy_class"] == "local_only"
    cloud = read(consolidate.key_for(s), "details")["content"]
    assert "Nginx" in cloud and "4521" not in cloud
    assert "error" in read(consolidate.key_for(s, "local"))                           # a cloud reader never gets it
    assert "4521" in read(consolidate.key_for(s, "local"), "details", privacy="local_only")["content"]
    with pytest.raises(psycopg.errors.RaiseException):                                # no looser version, ever
        with connection() as conn:
            conn.execute("""insert into views.version (view_key, depth, version, content, builder, privacy_class)
                            values (%s, 'overview', 99, 'sans le code', 'pytest', 'cloud_allowed')""",
                         (consolidate.key_for(s, "local"),))
    with pytest.raises(psycopg.errors.RaiseException):                                # no declassification
        with connection() as conn:
            conn.execute("update views.view set privacy_class = 'cloud_allowed' where view_key = %s",
                         (consolidate.key_for(s, "local"),))
    with connection() as conn:   # adding local evidence to a cloud view tightens it: it is no longer served to the cloud
        conn.execute("""insert into views.evidence (view_key, ref_kind, ref_id, privacy_class, added_by)
                        values (%s, 'event', 'x', 'local_only', 'pytest')""", (consolidate.key_for(s),))
    assert "error" in read(consolidate.key_for(s))


def test_shadow_views_are_not_served_by_default():
    t = f"s-{uuid.uuid4().hex[:8]}"
    say("dsh", t, "owner", "on garde Rust pour l'outil", NOW - timedelta(hours=3))
    extract("dsh", t, [{"kind": "decision", "text": "L'outil sera en Rust", "stage": "decided", "msgs": [1],
                        "quote": "on garde Rust pour l'outil"}])
    s = subject_with(("dsh", t))
    consolidate.build_subject(s)
    assert "error" in views.read({"depth": "overview", "key": consolidate.key_for(s)})
    assert "Rust" in read(consolidate.key_for(s))["content"]


def test_reconsolidation_proposals_are_validated_and_only_recorded_in_shadow():
    t = f"r-{uuid.uuid4().hex[:8]}"
    texts = ["on garde Redis pour le cache", "le cache utilise Redis", "on passe à Valkey pour le cache",
             "attends avant de toucher au cache"]
    for k, tx in enumerate(texts):
        say("claude_code", t, "owner", tx, NOW - timedelta(hours=6 - k))
    extract("claude_code", t, [{"kind": "decision", "text": "Le cache utilise Redis", "stage": "decided", "msgs": [1], "quote": texts[0]},
                               {"kind": "decision", "text": "Redis est le cache", "stage": "decided", "msgs": [2], "quote": texts[1]},
                               {"kind": "decision", "text": "Le cache passe à Valkey", "stage": "decided", "msgs": [3], "quote": texts[2]},
                               {"kind": "constraint", "text": "Attendre avant de toucher au cache", "scope": "task", "msgs": [4], "quote": texts[3]}])
    s = subject_with(("claude_code", t))
    with connection() as conn:
        ids = {r["content"]: r["item_id"][:8] for r in conn.execute(
            "select item_id::text, content from core.derived_items where source_refs->>'thread' = %s and kind <> 'summary'", (t,))}

    def chat(messages, **kw):
        return {"content": json.dumps({
            "merge": [[ids["Le cache utilise Redis"], ids["Redis est le cache"]], ["nope", "zzz"]],
            "supersede": [{"old": ids["Le cache utilise Redis"], "new": ids["Le cache passe à Valkey"], "why": "changement"}],
            "expire": [{"id": ids["Attendre avant de toucher au cache"], "why": "travail fait"},
                       {"id": ids["Le cache passe à Valkey"], "why": "pas une règle de tâche"}]}), "model": "scripted"}
    r = consolidate.reconsolidate(s, chat=chat, apply=False)
    assert len(r["proposals"]["merge"]) == 1 and len(r["proposals"]["supersede"]) == 1 and len(r["proposals"]["expire"]) == 1
    with connection() as conn:   # shadow: nothing changed
        assert conn.execute("select count(*) n from core.derived_items where source_refs->>'thread' = %s and status = 'superseded'",
                            (t,)).fetchone()["n"] == 0
    consolidate.reconsolidate(s, chat=chat, apply=True)
    consolidate.build_subject(s)
    ov = read(consolidate.key_for(s))["content"]
    assert "Valkey" in ov and "Le cache utilise Redis" not in ov and "Attendre avant" not in ov


@pytest.mark.parametrize("raw,owner_msg,agent_msg,stage", [
    ({"kind": "decision", "stage": "executed"}, True, False, "decided"),     # a request is not an execution
    ({"kind": "decision", "stage": "executed"}, True, True, "executed"),     # reported done (still not "verified")
    ({"kind": "decision", "stage": "proposed"}, False, True, "proposed"),    # W.Alter's proposal kept as such
    ({"kind": "decision", "stage": "decided"}, False, True, None),           # never the owner's choice without him
    ({"kind": "goal", "stage": None}, True, False, "requested"),
    ({"kind": "decision", "stage": "verified"}, True, True, "requested"),    # "verified" is never taken from a model
])
def test_stages_of_an_intention(raw, owner_msg, agent_msg, stage):
    seg = []
    if owner_msg:
        seg.append({"event_type": "message.sent", "content": "tu peux déployer le site ce soir"})
    if agent_msg:
        seg.append({"event_type": "message.received", "content": "Je propose de déployer le site ce soir, c'est fait"})
    item = {**raw, "text": "Déployer le site ce soir", "msgs": list(range(1, len(seg) + 1)), "quote": "déployer le site ce soir"}
    it, why = extract2.validate(item, seg, {})
    assert (it["stage"] if it else None) == stage


def test_until_scope_sets_a_validity_end():
    seg = [{"event_type": "message.sent", "content": "jusqu'au 15 décembre, pas de déploiement le week-end"}]
    it, _ = extract2.validate({"kind": "constraint", "text": "Pas de déploiement le week-end", "scope": "until",
                               "until": "2026-12-15", "msgs": [1], "quote": "pas de déploiement le week-end"}, seg, {})
    assert it["scope"] == "until" and it["until"].date().isoformat() == "2026-12-15"


def test_read_owner_message_cited_by_nothing_stays_verbatim_for_a_day():
    t = f"u-{uuid.uuid4().hex[:8]}"
    say("codex", t, "owner", "et surtout préviens Hani avant samedi", NOW - timedelta(minutes=40))
    say("codex", t, "owner", "ok merci", NOW - timedelta(minutes=39))
    extract("codex", t, [])          # read, the model kept nothing
    st = working.state("codex", t)
    assert [p["text"] for p in st["pending"] if not p.get("last")] == ["et surtout préviens Hani avant samedi"]
    assert "sans connaissance extraite" in st["text"]


def test_budget_never_drops_rules_silently():
    t = f"b-{uuid.uuid4().hex[:8]}"
    st = {"interpreted": {k: [] for k in working.KINDS}, "pending": [], "plan": None, "question": None}
    st["interpreted"]["constraint"] = [{"id": uuid.uuid4().hex, "text": f"Règle numéro {k} " + "très importante " * 12,
                                        "stage": "stated", "scope": "durable", "epistemic": "stated_owner", "at": NOW}
                                       for k in range(30)]
    text = working.render(st)
    assert len(text) // 4 < 600 and "+" in text and "non affichés faute de place" in text
    assert "Règle numéro 29" in text                                     # the most recent stays
