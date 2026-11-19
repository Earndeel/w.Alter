"""Lot 1 of the consolidation loop (2026-11-19) on the test database: typed statements with their own domain, test
data never kept, transient states that expire; reconciliation through Walter Decision (scripted llm.decide, one
batched decision, memoised); a decision and a goal that evolve several times across two conversations and runtimes;
the proof ladder (an agent's report is never a verification); Run Plane tasks closing goals; contradictions kept
until settled; the history of a piece of knowledge; a tagged run undone exactly, evidence on existing items
included; a pilot that never touches served knowledge and replays idempotently."""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from walter_memory import events, extract2, knowledge, llm
from walter_memory.db import connection

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    from walter_memory import quota, search
    monkeypatch.setattr(quota, "codex", lambda **k: {"ok": True})
    monkeypatch.setattr(search, "reindex_derived", lambda ids: {})       # the index is not under test here
    extract2.set_v1_start(NOW - timedelta(days=1))
    yield


def tag() -> str:
    return uuid.uuid4().hex[:6]


def say(source, thread_id, who, text, at):
    return events.record_events([{
        "event_type": "message.sent" if who == "owner" else "message.received", "source": source,
        "source_account": "pytest", "source_id": uuid.uuid4().hex, "thread_id": thread_id, "occurred_at": at,
        "content": text, "privacy_class": "cloud_allowed"}])["event_ids"][0]


def model(rule):
    """Scripted extraction: rule(numbered lines) → items (typed v3 format)."""
    def chat(messages, **kw):
        prompt = messages[0]["content"]
        part = prompt.split("Messages à analyser (numérotés, seuls citables) :", 1)[1].split("\n\nRends un JSON", 1)[0]
        lines = [l for l in part.strip().splitlines() if re.match(r"^\d+\. \[", l)]
        return {"content": json.dumps({"summary": "", "items": rule(lines)}), "cost_usd": 0, "model": "scripted"}
    return chat


def line_no(lines, needle):
    return next(i for i, l in enumerate(lines, 1) if needle in l)


class Decide:
    """Scripted Walter Decision: verdict(statement text, {K: item text}) → (verdict, K | 'none')."""
    def __init__(self, verdict):
        self.verdict, self.calls = verdict, []

    def __call__(self, state, questions, **kw):
        self.calls.append({"state": state, "questions": questions, **kw})
        ans = {}
        for sid, st in state["statements"].items():
            crit = {k: v for k, v in questions[f"{sid}_target"]["criteria"].items() if k != "none"}
            v, k = self.verdict(st["text"], {k: state["items"][k]["text"] for k in crit})
            ans[f"{sid}_target"] = {"choice": k if k in crit else "none", "confidence": 0.9}
            ans[f"{sid}_verdict"] = {"choice": v, "confidence": 0.9}
        return {"answers": ans, "model": "scripted-decision"}


def current(thread_id=None, *, word=None, kind=None, gen="g1"):
    with connection() as conn:
        return conn.execute("""select item_id::text, kind, content, status, stage, epistemic, scope, valid_to,
                                      lineage_id::text, attributes, source_event_ids
                               from core.derived_items where derived_by = 'l3.extract' and kind <> 'summary'
                                 and generation = %s and status in ('derived', 'verified')
                                 and (%s::text is null or source_refs->>'thread' = %s
                                      or coalesce(attributes->'threads', '[]'::jsonb) ? ((source_refs->>'source') || '/' || %s))
                                 and (%s::text is null or content ilike '%%' || %s || '%%')
                                 and (%s::text is null or kind = %s) order by created_at""",
                            (gen, thread_id, thread_id, thread_id, word, word, kind, kind)).fetchall()


# ───────────────────────────── extraction ─────────────────────────────
def test_each_statement_has_its_own_domain_and_test_data_is_never_kept():
    t, x = f"k-{tag()}", tag()
    say("claude_code", t, "owner", f"Pour le projet Orque{x} on garde Postgres, et de manière générale réponds-moi "
                                   f"toujours en français. Ceci est juste un exemple fictif de test.", NOW - timedelta(hours=2))

    def rule(lines):
        return [{"type": "decision", "text": f"Le projet Orque{x} garde Postgres", "author": "monsieur", "domain": "projet",
                 "project": f"Orque{x}", "msgs": [1], "quote": f"Pour le projet Orque{x} on garde Postgres"},
                {"type": "preference", "text": "Monsieur veut des réponses en français", "author": "monsieur",
                 "domain": "personnel", "project": f"Orque{x}", "msgs": [1], "quote": "réponds-moi toujours en français"},
                {"type": "fait", "text": "Un exemple fictif", "domain": "test", "msgs": [1],
                 "quote": "Ceci est juste un exemple fictif de test"}]
    extract2.process_thread("claude_code", t, chat=model(rule), force=True)
    got = {i["kind"]: i for i in current(t)}
    assert set(got) == {"decision", "preference"}                        # the test statement is not knowledge
    assert got["decision"]["attributes"]["domain"] == "project"
    assert got["decision"]["attributes"]["projects"] == [f"orque{x}"]   # its own project, nothing else
    assert got["preference"]["attributes"]["domain"] == "personal" and "project" not in got["preference"]["attributes"]
    with connection() as conn:
        rej = conn.execute("select rejected from extraction.segments where thread_id = %s", (t,)).fetchone()["rejected"]
    assert [r["reason"] for r in rej] == ["test"]


def test_a_transient_state_expires_and_an_agent_claim_is_only_a_declared_fact():
    t = f"k-{tag()}"
    say("codex", t, "owner", "où en est le serveur ?", NOW - timedelta(hours=2))
    say("codex", t, "agent", "Le serveur de build est en panne depuis ce matin, le disque est plein.",
        NOW - timedelta(hours=2) + timedelta(seconds=5))

    def rule(lines):
        return [{"type": "etat", "text": "Le serveur de build est en panne", "author": "walter", "domain": "projet",
                 "project": "build", "msgs": [2], "quote": "Le serveur de build est en panne depuis ce matin"},
                {"type": "fait", "text": "Le disque du serveur de build est plein", "author": "walter",
                 "domain": "projet", "project": "build", "msgs": [2], "quote": "le disque est plein"}]
    extract2.process_thread("codex", t, chat=model(rule), force=True)
    got = {i["attributes"]["act"]: i for i in current(t)}
    assert got["state"]["valid_to"] is not None and got["state"]["valid_to"] < NOW + timedelta(days=8)
    assert got["fact"]["epistemic"] == "agent_reported" and got["fact"]["stage"] == "stated"


# ───────────────────────────── reconciliation ─────────────────────────────
@pytest.mark.real_reconcile
def test_a_decision_evolves_three_times_across_two_conversations_with_one_batched_decision_each(monkeypatch):
    x = tag()
    a, b = f"ka-{x}", f"kb-{x}"
    monkeypatch.setattr(extract2, "KNOWN_SIMILAR", 0)
    monkeypatch.setattr(knowledge, "SEARCH", False)

    def pool(conn, st, pool_, gens, k):       # candidates: this test's items only (the test database keeps old runs)
        rows = conn.execute("""select item_id::text, kind, content, stage, scope, epistemic, status, generation,
                                      lineage_id::text, privacy_class, attributes, coalesce(valid_from, created_at) as at
                               from core.derived_items where derived_by = 'l3.extract' and status in ('derived','verified')
                                 and content like %s and generation = any(%s)""", (f"%{x}%", gens)).fetchall()
        return rows + [p for p in pool_ if p["item_id"].startswith("seg:")]
    monkeypatch.setattr(knowledge, "candidates", pool)

    def verdict(text, items):
        k = next(iter(items), None)
        if "Redis" in text:
            return "replaces", k
        if "persistance" in text:
            return "corrects", k
        if "je confirme" in text.lower() or text.endswith("(rappel)"):
            return "confirms", k
        return "new", None
    d = Decide(verdict)
    monkeypatch.setattr(llm, "decide", d)

    def decision(word, needle=None):
        def rule(lines):
            i = line_no(lines, needle or word)
            return [{"type": "decision", "text": f"Le cache du projet Lynx{x} : {word}", "author": "monsieur",
                     "domain": "projet", "project": f"lynx{x}", "msgs": [i], "quote": lines[i - 1].split("] ", 1)[1][:60]}]
        return rule
    say("claude_code", a, "owner", "pour le cache on garde Valkey sur ce projet", NOW - timedelta(hours=5))
    extract2.process_thread("claude_code", a, chat=model(decision("Valkey")), force=True)
    assert len(d.calls) == 0                                     # no candidate: new, without asking anyone
    say("codex", b, "owner", "finalement on passe le cache à Redis sur ce projet", NOW - timedelta(hours=4))
    extract2.process_thread("codex", b, chat=model(decision("Redis")), force=True)
    say("claude_code", a, "owner", "non, on revient à Valkey mais avec la persistance activée", NOW - timedelta(hours=3))
    extract2.process_thread("claude_code", a, chat=model(decision("Valkey avec persistance", "persistance")), force=True)
    assert len(d.calls) == 2 and all(c["processor"] == knowledge.NEED for c in d.calls)
    cur = [i for i in current(word=f"Lynx{x}")]
    assert [i["content"] for i in cur] == [f"Le cache du projet Lynx{x} : Valkey avec persistance"]   # one current version
    h = knowledge.history(cur[0]["item_id"])
    assert [v["status"] for v in h["versions"]] == ["superseded", "superseded", "derived"]
    assert [v["content"].rsplit(": ", 1)[1] for v in h["versions"]] == ["Valkey", "Redis", "Valkey avec persistance"]
    assert all(v["valid_to"] for v in h["versions"][:2])                 # replaced knowledge is no longer current
    ops = [(c["op"], c["verdict"]) for c in h["changes"]]
    assert ("supersede", "replaces") in ops and ("supersede", "corrects") in ops
    assert len({v["item_id"] for v in h["versions"]}) == 3 and h["lineage"]


@pytest.mark.real_reconcile
def test_an_assistant_claim_never_replaces_the_owner_and_the_contradiction_stays_until_he_settles_it(monkeypatch):
    x = tag()
    t = f"kc-{x}"
    monkeypatch.setattr(extract2, "KNOWN_SIMILAR", 0)
    monkeypatch.setattr(knowledge, "SEARCH", False)
    def verdict(text, items):
        if "est sous systemd" in text:            # the owner takes the assistant's side
            return "confirms", next(k for k, v in items.items() if "systemd" in v)
        return "replaces", next(iter(items), None)
    monkeypatch.setattr(llm, "decide", Decide(verdict))

    def item(text, author, needle):
        def rule(lines):
            i = line_no(lines, needle)
            return [{"type": "fait", "text": text, "author": author, "domain": "projet", "project": f"heron{x}",
                     "msgs": [i], "quote": needle}]
        return model(rule)
    say("dsh", t, "owner", f"le service Héron{x} tourne sous Docker", NOW - timedelta(hours=5))
    extract2.process_thread("dsh", t, chat=item(f"Héron{x} tourne sous Docker", "monsieur", "tourne sous Docker"), force=True)
    say("dsh", t, "owner", f"tu peux regarder Héron{x} ?", NOW - timedelta(hours=4))
    say("dsh", t, "agent", f"En fait Héron{x} ne tourne plus sous Docker, tout est sous systemd.",
        NOW - timedelta(hours=4) + timedelta(seconds=30))
    extract2.process_thread("dsh", t, chat=item(f"Héron{x} tourne sous systemd", "walter", "tout est sous systemd"), force=True)
    got = {i["content"]: i for i in current(t)}
    assert got[f"Héron{x} tourne sous Docker"]["attributes"]["contested"] is True       # flagged, still current
    assert got[f"Héron{x} tourne sous systemd"]["attributes"]["contested"] is True
    assert got[f"Héron{x} tourne sous systemd"]["epistemic"] == "agent_reported"
    say("dsh", t, "owner", f"oui c'est vrai, Héron{x} est sous systemd maintenant", NOW - timedelta(hours=3))
    extract2.process_thread("dsh", t, chat=item(f"Héron{x} est sous systemd", "monsieur", "est sous systemd maintenant"),
                            force=True)
    final = [i["content"] for i in current(t)]
    assert final == [f"Héron{x} tourne sous systemd"]                     # settled by him: one current answer
    won = current(t)[0]
    assert "contested" not in won["attributes"] and won["attributes"]["confirmed_by_owner"] is True
    with connection() as conn:
        lost = conn.execute("""select status, attributes->>'superseded_how' how from core.derived_items
                               where content = %s""", (f"Héron{x} tourne sous Docker",)).fetchone()
    assert dict(lost) == {"status": "superseded", "how": "settled"}       # still in the history


@pytest.mark.real_reconcile
def test_a_batched_decision_is_asked_once_for_the_same_inputs(monkeypatch):
    d = Decide(lambda text, items: ("confirms", next(iter(items))))
    monkeypatch.setattr(llm, "decide", d)
    cand = {"item_id": str(uuid.uuid4()), "kind": "fact", "content": f"Le port de Merle{tag()} est 8080",
            "stage": "stated", "epistemic": "stated_owner", "at": NOW, "privacy_class": "cloud_allowed"}
    batch = [(f"s{i}", {"text": f"Le port de Merle est 8080 ({i})", "act": "fact", "stage": "stated",
                         "epistemic_v": "stated_owner", "at": NOW},
              [cand, {**cand, "item_id": "seg:0", "content": "Le port de Merle change"}]) for i in range(1, 6)]
    # an earlier statement of the same segment (seg:j) is a candidate too, but never a reference of the decision
    r1 = knowledge.judge(batch, privacy_class="cloud_allowed", budget="recurring")
    r2 = knowledge.judge(batch, privacy_class="cloud_allowed", budget="recurring")
    assert len(d.calls) == 1 and r1 == r2 and len(d.calls[0]["questions"]) == 10     # 5 statements, one decision
    assert all(v == ("confirms", cand["item_id"], 0.9) for v in r1.values())


# ───────────────────────────── lifecycle and proof ─────────────────────────────
def _session(thread_id, rows, start=0):
    sid = f"claude_code/vm/{thread_id}"
    with connection() as conn:
        conn.execute("""insert into walter_logs.sessions (session_id, runtime, native_id) values (%s, 'claude_code', %s)
                        on conflict do nothing""", (sid, thread_id))
        for k, (at, tool, cmd, status, out) in enumerate(rows):
            for typ, text, st in (("tool/call", cmd, None), ("tool/result", out, status)):
                conn.execute("""insert into walter_logs.events (session_id, seq, type, occurred_at, call_id, tool, status,
                                    text, privacy_class, source_ref)
                                values (%s, %s, %s, %s, %s, %s, %s, %s, 'cloud_allowed', %s)""",
                             (sid, start + k * 2 + (typ == "tool/result"), typ, at, f"c{start + k}", tool, st, text,
                              f"pytest:{start + k}:{typ}"))
    return sid


def _task(thread_id, at, status):
    run, task = str(uuid.uuid4()), str(uuid.uuid4())
    with connection() as conn:
        conn.execute("""insert into runs.runs (run_id, origin, status, started_at)
                        values (%s, %s, 'ended', %s)""", (run, json.dumps({"session_id": f"claude_code/vm/{thread_id}"}), at))
        conn.execute("""insert into runs.tasks (task_id, run_id, kind, status, started_at) values (%s, %s, 'objective', %s, %s)""",
                     (task, run, status, at))
    return task


def test_a_goal_moves_from_request_to_done_with_proof_never_on_the_agents_word_alone():
    x = tag()
    t = f"kg-{x}"
    t0 = NOW - timedelta(hours=6)
    say("claude_code", t, "owner", f"tu peux migrer le schéma Ibis{x} vers la version 2 ?", t0)
    say("claude_code", t, "agent", f"Je m'en occupe : je migre le schéma Ibis{x} maintenant.", t0 + timedelta(minutes=1))
    say("claude_code", t, "agent", f"C'est fait, le schéma Ibis{x} est migré en version 2.", t0 + timedelta(minutes=5))

    def ask(lines):
        return [{"type": "objectif", "text": f"Migrer le schéma Ibis{x} vers la version 2", "author": "monsieur",
                 "domain": "projet", "project": f"ibis{x}", "msgs": [1], "quote": f"migrer le schéma Ibis{x} vers la version 2"},
                {"type": "action", "stage": "annoncee", "text": f"W.Alter migre le schéma Ibis{x}", "author": "walter",
                 "domain": "projet", "project": f"ibis{x}", "msgs": [2], "quote": f"je migre le schéma Ibis{x} maintenant",
                 "about": None},
                {"type": "action", "stage": "terminee", "text": f"Le schéma Ibis{x} est migré en version 2",
                 "author": "walter", "domain": "projet", "project": f"ibis{x}", "msgs": [3],
                 "quote": f"le schéma Ibis{x} est migré en version 2"}]

    def as_progress(batch, **kw):            # the decision: both actions are about the goal of the same segment
        return {sid: ("enriches", next((c["item_id"] for c in cands if c["kind"] == "goal"), None), 0.9)
                for sid, st, cands in batch}
    import walter_memory.knowledge as kn
    orig, kn.judge = kn.judge, as_progress
    try:
        extract2.process_thread("claude_code", t, chat=model(ask), force=True)
        goals = current(t, kind="goal")
        assert len(goals) == 1 and len(current(t)) == 1                  # the steps are not goals of their own
        g = goals[0]
        assert g["stage"] == "executed" and g["status"] == "derived"     # reported done: no tool trace, not verified
        assert g["attributes"]["proof"]["level"] == "claimed"
        assert [p["stage"] for p in g["attributes"]["progress"]] == ["open", "executed"]
        # the check, as the session ran it: tests passed after the migration
        say("claude_code", t, "owner", "et tu as vérifié ?", t0 + timedelta(minutes=7))
        _session(t, [(t0 + timedelta(minutes=8), "Bash", "walter-python -m pytest -q tests/test_ibis.py", "ok",
                      "12 passed in 0.4s")])
        say("claude_code", t, "agent", f"Vérifié : les tests du schéma Ibis{x} passent (12 passed).",
            t0 + timedelta(minutes=9))

        def result(lines):
            i = line_no(lines, "Vérifié")
            return [{"type": "resultat", "text": f"Les tests du schéma Ibis{x} passent après la migration",
                     "author": "walter", "domain": "projet", "project": f"ibis{x}", "msgs": [i],
                     "quote": f"les tests du schéma Ibis{x} passent"}]
        extract2.process_thread("claude_code", t, chat=model(result), force=True)
        g = current(t, kind="goal")[0]
        assert g["stage"] == "verified" and g["status"] == "verified"
        assert g["attributes"]["proof"]["level"] == "checked" and g["attributes"]["proof"]["checks_ok"] == 1
        # the Run Plane task the request started is done: the goal is closed
        _task(t, t0 + timedelta(seconds=20), "done")
        say("claude_code", t, "owner", "merci", t0 + timedelta(minutes=12))
        extract2.process_thread("claude_code", t, chat=model(lambda lines: []), force=True)
        with connection() as conn:
            g = conn.execute("select stage, attributes from core.derived_items where item_id = %s",
                             (g["item_id"],)).fetchone()
        assert g["stage"] == "done" and g["attributes"]["task_id"]
        ops = [(c["op"], c["reason"]) for c in knowledge.history(goals[0]["item_id"])["changes"]]
        assert ops[0][0] == "create" and ops[-1] == ("advance", "task done")   # every move is in its history
        assert [r for o, r in ops if o == "advance"][:3] == ["requested→accepted", "accepted→executed", "executed→verified"]
    finally:
        kn.judge = orig


def test_a_failing_check_leaves_the_report_unverified_and_a_cancelled_task_cancels_the_goal():
    x = tag()
    t = f"kf-{x}"
    t0 = NOW - timedelta(hours=6)
    say("claude_code", t, "owner", f"tu peux réparer l'export Pinson{x} ?", t0)
    _session(t, [(t0 + timedelta(minutes=2), "Bash", "walter-python -m pytest -q tests/test_export.py", "error",
                  "2 failed, 10 passed")])
    say("claude_code", t, "agent", f"Réparé, l'export Pinson{x} fonctionne, les tests passent.", t0 + timedelta(minutes=3))

    def rule(lines):
        return [{"type": "objectif", "text": f"Réparer l'export Pinson{x}", "author": "monsieur", "domain": "projet",
                 "project": f"pinson{x}", "msgs": [1], "quote": f"réparer l'export Pinson{x}"},
                {"type": "resultat", "text": f"L'export Pinson{x} fonctionne", "author": "walter", "domain": "projet",
                 "project": f"pinson{x}", "msgs": [2], "quote": f"l'export Pinson{x} fonctionne"}]
    import walter_memory.knowledge as kn
    orig = kn.judge
    kn.judge = lambda batch, **kw: {sid: ("enriches", next((c["item_id"] for c in cands if c["kind"] == "goal"), None),
                                          0.9) for sid, st, cands in batch}
    try:
        extract2.process_thread("claude_code", t, chat=model(rule), force=True)
    finally:
        kn.judge = orig
    g = current(t, kind="goal")[0]
    assert g["stage"] == "executed" and g["attributes"]["proof"]["level"] == "refuted"    # the agent said so; the test failed
    assert g["attributes"]["proof"]["tools_error"] == 1
    _task(t, t0 + timedelta(seconds=10), "cancelled")
    say("claude_code", t, "owner", "laisse tomber", t0 + timedelta(minutes=30))
    extract2.process_thread("claude_code", t, chat=model(lambda lines: []), force=True)
    with connection() as conn:
        assert conn.execute("select stage from core.derived_items where item_id = %s",
                            (g["item_id"],)).fetchone()["stage"] == "cancelled"


# ───────────────────────────── revert, pilot, replay ─────────────────────────────
def _image(ids):
    with connection() as conn:
        items = [dict(r) for r in conn.execute("""select item_id::text, status, stage, valid_to, attributes, epistemic,
                                                         source_event_ids from core.derived_items
                                                  where item_id = any(%s::uuid[]) order by 1""", (ids,))]
        prov = conn.execute("""select count(*) n from core.provenance where target_table = 'derived_items'
                               and (target_id = any(%s::text[]) or source_id = any(%s::text[]))""",
                            (ids, ids)).fetchone()["n"]
    return items, prov


def _goal_and_rule(t, x, t0):
    say("claude_code", t, "owner", f"tu peux préparer le rapport Grive{x} ? et jamais de push le vendredi", t0)

    def rule(lines):
        return [{"type": "objectif", "text": f"Préparer le rapport Grive{x}", "author": "monsieur", "domain": "projet",
                 "project": f"grive{x}", "msgs": [1], "quote": f"tu peux préparer le rapport Grive{x}"},
                {"type": "contrainte", "text": "Jamais de push le vendredi", "author": "monsieur", "domain": "projet",
                 "project": f"grive{x}", "msgs": [1], "quote": "jamais de push le vendredi"}]
    extract2.process_thread("claude_code", t, chat=model(rule), force=True)
    return {i["kind"]: i for i in current(t)}


def _later(t, x, t0):
    a = say("claude_code", t, "owner", f"je confirme : jamais de push le vendredi sur Grive{x}", t0 + timedelta(hours=1))
    b = say("claude_code", t, "agent", f"Le rapport Grive{x} est prêt et envoyé.", t0 + timedelta(hours=1, minutes=5))

    def rule(lines):
        out = []
        for i, l in enumerate(lines, 1):
            if "je confirme" in l:
                out.append({"type": "contrainte", "text": "Jamais de push le vendredi", "author": "monsieur",
                            "domain": "projet", "project": f"grive{x}", "msgs": [i], "quote": "jamais de push le vendredi"})
            if "est prêt" in l:
                out.append({"type": "action", "stage": "terminee", "text": f"Le rapport Grive{x} est prêt",
                            "author": "walter", "domain": "projet", "project": f"grive{x}", "msgs": [i],
                            "quote": f"Le rapport Grive{x} est prêt et envoyé"})
        return out
    return [a, b], rule


def test_reverting_a_tagged_run_restores_existing_items_and_their_evidence_exactly(monkeypatch):
    x = tag()
    t = f"kr-{x}"
    t0 = NOW - timedelta(hours=8)
    base = _goal_and_rule(t, x, t0)
    ids = [base["goal"]["item_id"], base["constraint"]["item_id"]]
    before = _image(ids)
    seeds, rule = _later(t, x, t0)
    monkeypatch.setattr(knowledge, "judge", lambda batch, **kw: {
        sid: ("confirms" if st["kind"] == "constraint" else "enriches",
              next(c["item_id"] for c in cands if c["kind"] == ("constraint" if st["kind"] == "constraint" else "goal")),
              0.9) for sid, st, cands in batch})
    r = extract2.backfill(seeds, tag=f"pytest-rv-{x}", chat=model(rule), workers=1, window=0)   # served generation
    assert r["reused"] == 1 and r["advanced"] == 1 and r["items"] == 0
    after = _image(ids)
    assert after != before
    got = {i["item_id"]: i for i in after[0]}
    assert got[base["goal"]["item_id"]]["stage"] == "executed"
    assert len(got[base["constraint"]["item_id"]]["source_event_ids"]) == 2
    rv = extract2.backfill_revert(f"pytest-rv-{x}", confirm=True)
    assert rv["gate"]["restored"] == 2 and rv["gate"]["kept_later_edits"] == 0
    assert _image(ids) == before                                          # evidence, stage, attributes, provenance


def test_a_pilot_never_changes_served_knowledge_replays_idempotently_and_reverts(monkeypatch):
    x = tag()
    t = f"kp-{x}"
    t0 = NOW - timedelta(hours=8)
    base = _goal_and_rule(t, x, t0)
    ids = [base["goal"]["item_id"], base["constraint"]["item_id"]]
    before = _image(ids)
    seeds, rule = _later(t, x, t0)
    monkeypatch.setattr(knowledge, "judge", lambda batch, **kw: {
        sid: ("confirms" if st["kind"] == "constraint" else "enriches",
              next(c["item_id"] for c in cands if c["kind"] == ("constraint" if st["kind"] == "constraint" else "goal")),
              0.9) for sid, st, cands in batch})
    tg = f"pytest-pl-{x}"
    r = extract2.backfill(seeds, tag=tg, chat=model(rule), workers=1, window=0, generation=extract2.STAGING)
    assert r["staged"] == 2 and _image(ids) == before                    # recorded, not applied
    with connection() as conn:
        st = conn.execute("""select op, staged from core.derived_changes where tag = %s order by change_id""",
                          (tg,)).fetchall()
    assert [(s["op"], s["staged"]) for s in st] == [("evidence", True), ("advance", True)]
    again = extract2.backfill(seeds, tag=tg, chat=model(rule), workers=1, window=0, generation=extract2.STAGING)
    assert again["segments"] == 0                                         # idempotent
    extract2.backfill_revert(tg, confirm=True)
    assert _image(ids) == before
    with connection() as conn:
        assert conn.execute("select count(*) n from core.derived_changes where tag = %s and reverted_at is null",
                            (tg,)).fetchone()["n"] == 0


def test_a_fact_enriching_another_is_a_linked_complement_both_current(monkeypatch):
    x = tag()
    t = f"ke-{x}"
    say("codex", t, "owner", f"rappelle-moi : le service Loriot{x} écoute sur le port 8080", NOW - timedelta(hours=3))
    extract2.process_thread("codex", t, chat=model(lambda lines: [
        {"type": "fait", "text": f"Le service Loriot{x} écoute sur le port 8080", "author": "monsieur", "domain": "projet",
         "project": f"loriot{x}", "msgs": [1], "quote": "écoute sur le port 8080"}]), force=True)
    first = current(t)[0]
    say("codex", t, "owner", f"et Loriot{x} tourne sous systemd", NOW - timedelta(hours=2))
    monkeypatch.setattr(knowledge, "judge", lambda batch, **kw: {sid: ("enriches", first["item_id"], 0.9)
                                                                 for sid, st, cands in batch})
    extract2.process_thread("codex", t, chat=model(lambda lines: [
        {"type": "fait", "text": f"Le service Loriot{x} tourne sous systemd", "author": "monsieur", "domain": "projet",
         "project": f"loriot{x}", "msgs": [line_no(lines, "systemd")], "quote": "tourne sous systemd"}]), force=True)
    cur = {i["content"]: i for i in current(t)}
    assert len(cur) == 2 and first["item_id"] in {i["item_id"] for i in cur.values()}     # nothing replaced
    assert cur[f"Le service Loriot{x} tourne sous systemd"]["attributes"]["enriches"] == first["item_id"]
    with connection() as conn:
        assert conn.execute("""select count(*) n from core.provenance where role = 'enriches' and source_id = %s""",
                            (first["item_id"],)).fetchone()["n"] == 1


def test_a_report_a_help_page_or_an_admitted_gap_is_never_a_verification():
    x = tag()
    t = f"kv-{x}"
    t0 = NOW - timedelta(hours=6)
    say("claude_code", t, "owner", f"tu peux activer la règle Mésange{x} ?", t0)
    _session(t, [(t0 + timedelta(minutes=1), "Bash", "walter-tools --help", "ok", "usage: walter-tools ..."),
                 (t0 + timedelta(minutes=2), "mcp__ccd_turn__wrap_up", '{"recap": "règle activée et vérifiée"}', "ok", "ok")])
    say("claude_code", t, "agent", f"La règle Mésange{x} est activée, mais je n'ai pas pu vérifier de bout en bout.",
        t0 + timedelta(minutes=3))
    with connection() as conn:
        pr = knowledge.proof(conn, "claude_code", t, t0 + timedelta(minutes=3))
    assert pr["level"] == "executed" and pr["checks"] == 0               # neither is a check
    _session(t, [(t0 + timedelta(minutes=2, seconds=30), "Bash", "curl -s -o /dev/null -w '%{http_code}' https://x", "ok",
                  "200")], start=10)
    with connection() as conn:
        pr = knowledge.proof(conn, "claude_code", t, t0 + timedelta(minutes=3))
    assert pr["level"] == "checked" and pr["last_check"]["cmd"].startswith("curl")
    st = {"text": f"La règle Mésange{x} est activée, mais W.Alter n'a pas pu vérifier de bout en bout"}
    assert not knowledge.verifies(st, pr)                                  # the statement admits the gap
    assert knowledge.verifies({"text": f"La règle Mésange{x} répond 200"}, pr)


def test_a_pilot_complement_of_served_knowledge_is_recorded_never_linked_across_generations(monkeypatch):
    x = tag()
    t = f"kx-{x}"
    say("codex", t, "owner", f"note : le service Pipit{x} écoute sur le port 9090", NOW - timedelta(hours=3))
    extract2.process_thread("codex", t, chat=model(lambda lines: [
        {"type": "fait", "text": f"Le service Pipit{x} écoute sur le port 9090", "author": "monsieur", "domain": "projet",
         "project": f"pipit{x}", "msgs": [1], "quote": "écoute sur le port 9090"}]), force=True)
    served = current(t)[0]
    seed = say("codex", t, "owner", f"et Pipit{x} tourne sous systemd", NOW - timedelta(hours=2))
    monkeypatch.setattr(knowledge, "judge", lambda batch, **kw: {sid: ("enriches", served["item_id"], 0.9)
                                                                 for sid, st, cands in batch})
    tg = f"pytest-px-{x}"
    r = extract2.backfill([seed], tag=tg, chat=model(lambda lines: [
        {"type": "fait", "text": f"Le service Pipit{x} tourne sous systemd", "author": "monsieur", "domain": "projet",
         "project": f"pipit{x}", "msgs": [line_no(lines, "systemd")], "quote": "tourne sous systemd"}]),
        workers=1, window=0, generation=extract2.STAGING)
    assert r["errors"] == 0 and r["items"] == 1
    with connection() as conn:
        link = conn.execute("select after from core.derived_changes where tag = %s and op = 'link'", (tg,)).fetchone()
    assert link["after"]["+links_not_applied"][0][1] == served["item_id"]
    extract2.backfill_revert(tg, confirm=True)


@pytest.mark.real_reconcile
def test_an_action_and_a_result_carry_out_the_owners_goal_across_conversations(monkeypatch):
    x = tag()
    a, b = f"kwa-{x}", f"kwb-{x}"
    t0 = NOW - timedelta(hours=8)
    monkeypatch.setattr(extract2, "KNOWN_SIMILAR", 0)
    monkeypatch.setattr(knowledge, "SEARCH", False)
    asked = []

    def decide(state, questions, **kw):
        asked.append(sorted(questions))
        ans = {}
        for sid in state["statements"]:
            ans[f"{sid}_target"] = {"choice": "none", "confidence": 0.9}
            ans[f"{sid}_verdict"] = {"choice": "new", "confidence": 0.9}
            if f"{sid}_work" in questions:
                k = next(k for k, v in questions[f"{sid}_work"]["criteria"].items() if f"Roitelet{x}" in v)
                ans[f"{sid}_work"] = {"choice": k, "confidence": 0.9}
        return {"answers": ans, "model": "scripted-decision"}
    monkeypatch.setattr(llm, "decide", decide)
    say("claude_code", a, "owner", f"applique la maquette Roitelet{x} au tableau de bord", t0)
    extract2.process_thread("claude_code", a, chat=model(lambda lines: [
        {"type": "objectif", "text": f"Appliquer la maquette Roitelet{x} au tableau de bord", "author": "monsieur",
         "domain": "projet", "project": "dashboard", "msgs": [1], "quote": f"applique la maquette Roitelet{x}"}]), force=True)
    goal = current(a, kind="goal")[0]
    # another conversation: the work is done and checked there; the goal is found among similar open work
    monkeypatch.setattr(knowledge, "open_work", lambda pool, k=6: [
        {**goal, "content": goal["content"], "at": t0, "privacy_class": "cloud_allowed"}])
    say("claude_code", b, "owner", "tu en es où du tableau de bord ?", t0 + timedelta(hours=1))
    _session(b, [(t0 + timedelta(hours=1, minutes=2), "Bash", "walter-python -m pytest -q tests/test_ui.py", "ok",
                  "8 passed in 1.2s")])
    say("claude_code", b, "agent", "J'ai appliqué la maquette au tableau de bord, et les tests de l'interface passent.",
        t0 + timedelta(hours=1, minutes=3))
    extract2.process_thread("claude_code", b, chat=model(lambda lines: [
        {"type": "action", "stage": "terminee", "text": "W.Alter a appliqué la maquette au tableau de bord",
         "author": "walter", "domain": "projet", "project": "dashboard", "msgs": [line_no(lines, "appliqué")],
         "quote": "J'ai appliqué la maquette au tableau de bord"},
        {"type": "resultat", "text": "Les tests de l'interface du tableau de bord passent", "author": "walter",
         "domain": "projet", "project": "dashboard", "msgs": [line_no(lines, "appliqué")],
         "quote": "les tests de l'interface passent"}]), force=True)
    assert any("s1_work" in q for q in asked)                            # the declared question was asked
    assert [i["item_id"] for i in current(b)] == [goal["item_id"]]      # no separate item for the steps: the goal
    with connection() as conn:
        g = conn.execute("select stage, status, attributes from core.derived_items where item_id = %s",
                         (goal["item_id"],)).fetchone()
    assert g["stage"] == "verified" and g["status"] == "verified"
    assert [p["act"] for p in g["attributes"]["progress"]] == ["action", "result"]
    assert f"claude_code/{b}" in g["attributes"]["threads"]                # the goal is visible from both conversations


def test_an_unverified_declaration_never_overwrites_confirmed_knowledge():
    """Production 19/11: a declaration that is not the owner's never replaces knowledge confirmed by him or proven
    by a check — it is contested; an enrichment of it stays a linked complement."""
    agent = {"by_owner": False, "act": "fact", "kind": "fact"}
    proven = {"kind": "fact", "epistemic": "agent_reported", "status": "verified", "attributes": {}}
    endorsed = {"kind": "decision", "epistemic": "agent_reported", "status": "derived",
                "attributes": {"confirmed_by_owner": True}}
    checked = {"kind": "fact", "epistemic": "observed", "status": "derived",
               "attributes": {"proof": {"level": "checked"}}}
    plain = {"kind": "fact", "epistemic": "agent_reported", "status": "derived", "attributes": {}}
    for t in (proven, endorsed, checked):
        assert knowledge.guard(agent, "replaces", t, 0.9, 0.5) == ("contradicts", "unverified_vs_confirmed")
        assert knowledge.guard(agent, "corrects", t, 0.9, 0.5) == ("contradicts", "unverified_vs_confirmed")
    assert knowledge.guard({**agent, "kind": "decision", "act": "decision"}, "enriches", endorsed, 0.9, 0.5) \
        == ("enriches", "complement_only")
    assert knowledge.guard(agent, "replaces", plain, 0.9, 0.5) == ("replaces", None)      # declaration over declaration
    assert knowledge.guard({**agent, "by_owner": True}, "replaces", proven, 0.9, 0.5) == ("replaces", None)
