"""Memory V1 end-to-end checks (2026-11-03), THROWAWAY test database only: does the MODEL receive and use memory?

Each case writes its conversation as canonical events (what the runtime's connector would record), runs the real
pipeline (extract2 with the Router's memory_extraction poste, consolidation), then asks a REAL runtime through its
REAL hook — DSH headless (`dsh --profile headless`), whose UserPromptSubmit hook calls a test gateway (port 8990)
backed by the test database — and checks its answer. A control run with the hook's memory off shows the answer comes
from the injected context, not from the model. No memory reaches the production database: the DSH workspace is a bench
workspace (never ingested into core.events); only its run is a production run of channel `test` (walter-llm serves DSH
within an open run and caps a test run's paid spend).

  WALTER_MEMORY_DATABASE_URL=<test dsn> walter-python bench/e2e_v1.py decision [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DSN = os.environ.get("WALTER_MEMORY_DATABASE_URL", "")
def require_test_db() -> None:
    assert DSN and ":5433/" not in DSN, "e2e writes only to the test database (tests/testdb.sh up)"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_memory import events, extract2, generations, ingestion, llm, search  # noqa: E402
from walter_memory.db import connection  # noqa: E402

PORT = 8990
DSH = "/opt/dsh/node_modules/.bin/dsh"
NOW = datetime.now(timezone.utc)


# ───────────────────────────── harness ─────────────────────────────
class Gateway:
    """walter-memory-gateway on the test database (the real app, another port)."""
    def __enter__(self):
        env = {**os.environ, "WALTER_MEMORY_DATABASE_URL": DSN, "PGPASSFILE": "/root/.pgpass"}
        for line in Path("/walter/cognition/memory/.env").read_text().splitlines():   # the gateway token, as the unit loads it
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
        self.p = subprocess.Popen(["walter-python", "-m", "uvicorn", "walter_memory.gateway:app", "--host", "127.0.0.1",
                                   "--port", str(PORT), "--log-level", "warning"], env=env,
                                  cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        import urllib.request
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        return self

    def __exit__(self, *exc):
        self.p.terminate()
        self.p.wait(10)


def ask_dsh(prompt: str, *, memory: bool = True, timeout: int = 300, production: bool = False) -> dict:
    """One real DSH headless turn; its hook injects Walter's context from the TEST gateway (memory=False: control;
    production=True: the production gateway, read-only — the bench workspace keeps the session out of core.events)."""
    ws = tempfile.mkdtemp(prefix="walter-scenario-dsh-e2e-")
    # Only the memory context comes from the test gateway. The run is a production `test` run (walter-llm serves DSH
    # only within an open run and caps a test run's spend); the bench workspace keeps the session out of core.events.
    env = {k: v for k, v in os.environ.items() if k != "WALTER_MEMORY_DATABASE_URL"}
    env |= {"DSH_HOME": "/opt/dsh/test-home", "WALTER_MEMORY_URL": "http://127.0.0.1:8890" if production else f"http://127.0.0.1:{PORT}",
            "WALTER_HOOK_SKILLS": "off",
            "WALTER_HOOK_PREFLIGHT": "off", "WALTER_HOOK_VIEWS": "off", "WALTER_HOOK_CONTEXT": "on" if memory else "off",
            "WALTER_RUN_CHANNEL": "test"}
    t0 = time.time()
    out = subprocess.run([DSH, "--profile", "headless", "--json", prompt], capture_output=True, text=True, cwd=ws,
                         env=env, timeout=timeout)
    answer, sid = None, None
    for line in out.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "session":
            sid = ev.get("sessionId")
        elif ev.get("type") == "final":
            answer = ev.get("text")
    return {"answer": answer, "session": sid, "seconds": round(time.time() - t0, 1), "memory": memory,
            "rc": out.returncode, "stderr": out.stderr[-400:] if answer is None else ""}


def injected(prompt: str, session: str = "") -> dict:
    """What the hook's memory call returns for this prompt (same endpoint, same budget, same caller)."""
    import httpx
    from walter_memory import client
    r = httpx.post(f"http://127.0.0.1:{PORT}/v1/context", headers={"Authorization": f"Bearer {client.token()}"},
                   timeout=30, json={"query": prompt, "budget": {"profile": 0, "people": 300, "knowledge": 600,
                                                               "evidence": 300}, "include_profile": False,
                                     "caller": "dsh-hook", "mode": "on", "session_id": session or None})
    r.raise_for_status()
    return r.json()


def say(source, thread, who, text, at, privacy="cloud_allowed") -> str:
    return events.record_events([{"event_type": "message.sent" if who == "owner" else "message.received",
                                  "source": source, "source_account": "e2e", "source_id": uuid.uuid4().hex,
                                  "thread_id": thread, "occurred_at": at, "content": text,
                                  "privacy_class": privacy}])["event_ids"][0]


def items_of(thread: str) -> list[dict]:
    with connection() as conn:
        return conn.execute("""select item_id::text, kind, status, stage, scope, content from core.derived_items
                               where source_refs->>'thread' = %s and kind <> 'summary' order by created_at""",
                            (thread,)).fetchall()


def has(text: str | None, *words) -> bool:
    t = (text or "").lower()
    return any(w.lower() in t for w in words)


# ───────────────────────────── case 1: a decision changes, another runtime finds the current one ──────────────────
def setup() -> None:
    require_test_db()
    ingestion.register_connector("search_indexer", "walter", "agent", "e2e", timedelta(minutes=10))
    extract2.set_v1_start(NOW - timedelta(days=30))
    generations.rollback(confirm=True)


def case_decision() -> dict:
    """Conversation in Codex: a database choice, then the owner changes it and adds a rule. Extraction is real
    (Router memory_extraction). Then DSH — another runtime, a new session — is asked without tools."""
    setup()
    t = f"e2e-codex-{uuid.uuid4().hex[:8]}"
    turns = [
        ("owner", "Pour le projet Héliotrope (l'appli de réservation de la boulangerie de ma tante), on part sur "
                  "Supabase pour la base de données.", 50),
        ("agent", "Entendu : Supabase pour Héliotrope. Je prépare le schéma des réservations.", 49),
        ("owner", "Finalement non, oublie Supabase : pour Héliotrope on prend SQLite en local, c'est plus simple pour "
                  "la boulangerie. Et désormais, interdiction d'ajouter un service payant sans mon accord.", 20),
        ("agent", "Compris : SQLite en local pour Héliotrope, et aucun service payant sans votre accord.", 19),
    ]
    for who, text, minutes_ago in turns:
        say("codex", t, who, text, NOW - timedelta(minutes=minutes_ago))
    x = extract2.process_thread("codex", t, force=True, chat=llm.chat)
    search.index_pending()
    stored = items_of(t)
    q = ("Sans utiliser aucun outil, réponds en deux phrases courtes : pour le projet Héliotrope, quelle base de "
         "données a été retenue ? Ai-je le droit d'ajouter un service payant ?")
    with Gateway():
        ctx = injected(q)
        on = ask_dsh(q, memory=True)
        off = ask_dsh(q, memory=False)
    current = [i for i in stored if i["status"] in ("derived", "verified") and i["kind"] == "decision"
               and i["stage"] not in ("abandoned",)]
    ok_store = any("sqlite" in i["content"].lower() for i in current) and \
        not any("supabase" in i["content"].lower() and "sqlite" not in i["content"].lower() for i in current)
    ok_ctx = has(ctx["text"], "sqlite")
    ok_on = has(on["answer"], "sqlite") and has(on["answer"], "accord", "non", "pas le droit", "interdit")
    ok_off = not has(off["answer"], "sqlite")
    return {"case": "decision", "thread": t, "extraction": x, "stored": stored, "injected_text": ctx["text"],
            "injected_tokens": ctx["trace"]["total_tokens"], "trace": ctx["trace"].get("sections"), "with_memory": on, "control_without_memory": off,
            "checks": {"current_decision_stored_old_superseded": ok_store, "injected": ok_ctx,
                       "model_used_it": ok_on, "control_does_not_know": ok_off},
            "pass": ok_store and ok_ctx and ok_on and ok_off}


# ───────────────────────────── case 2: a word not interpreted yet survives the switch to another runtime ───────────
def case_working() -> dict:
    """Codex: the owner gives an instruction; NO extraction has run yet (it is only in the canonical events). The
    thread belongs to a subject (as the attachment engine records it). DSH, a new session that picks the work up, is
    asked: the working state carries the owner's words verbatim (subject recognised by local similarity)."""
    setup()
    from walter_memory import consolidate
    t, key = f"e2e-codex-{uuid.uuid4().hex[:8]}", f"subject:e2e{uuid.uuid4().hex[:6]}"
    words = ("Pour Héliotrope, affiche tous les prix en bahts (THB), jamais en euros, et garde le menu en thaï et en "
             "français.")
    say("codex", t, "owner", words, NOW - timedelta(minutes=6))
    say("codex", t, "agent", "Je note pour les prix et le menu d'Héliotrope.", NOW - timedelta(minutes=5))
    title = "Héliotrope : appli de réservation de la boulangerie"
    with connection() as conn:
        conn.execute("""insert into views.view (view_key, domain, horizon, title, first_at, last_at, generation)
                        values (%s, 'projects', 'medium', %s, now() - interval '1 hour', now(), 'g0')""", (key, title))
        conn.execute("""insert into views.member (session_id, seq, view_key, occurred_at, runtime, attached_by)
                        values (%s, 1, %s, now() - interval '6 minutes', 'codex', 'rule')""", (f"codex/vm/{t}", key))
        consolidate.set_embedding(conn, key, title + " — application de réservation pour la boulangerie, prix, menu")
    q = ("On reprend Héliotrope, l'appli de réservation de la boulangerie. Sans utiliser aucun outil, réponds en une "
         "phrase : dans quelle devise dois-je afficher les prix, et dans quelles langues le menu ?")
    with Gateway():
        ctx = injected(q, session=f"e2e-dsh-{uuid.uuid4().hex[:6]}")
        on = ask_dsh(q, memory=True)
        off = ask_dsh(q, memory=False)
    ok_ctx = "bahts (THB)" in ctx["text"]
    ok_on = has(on["answer"], "thb", "baht") and has(on["answer"], "thaï", "thai")
    ok_off = not has(off["answer"], "thb", "baht")
    return {"case": "working", "thread": t, "subject": key, "injected_text": ctx["text"],
            "injected_tokens": ctx["trace"]["total_tokens"], "trace": ctx["trace"].get("sections"), "with_memory": on, "control_without_memory": off,
            "checks": {"verbatim_in_working_state": ok_ctx, "model_used_it": ok_on, "control_does_not_know": ok_off},
            "pass": ok_ctx and ok_on and ok_off}


def gps(lat, lng, t, wifi=None):
    events.record_events([{"event_type": "location.sample", "source": "overland", "source_account": "e2e",
                           "source_id": uuid.uuid4().hex, "occurred_at": t, "privacy_class": "local_only",
                           "payload": {"lat": lat, "lng": lng, "accuracy_m": 10,
                                       "raw": {"properties": {"wifi": wifi, "motion": ["stationary"]}}}}])


def episode_view(title_part: str, local: bool) -> dict | None:
    with connection() as conn:
        return conn.execute("""select view_key, epistemic, privacy_class, title from views.view where kind = 'episode'
                               and title ilike %s and (view_key like '%%:local') = %s order by updated_at desc limit 1""",
                            (f"%{title_part}%", local)).fetchone()


# ───────────────────────────── case 3: several sources, one episode, hypotheses stay hypotheses ─────────────────────
def case_episode() -> dict:
    """Calendar (cloud) + a Beeper conversation that plans it (pseudonymised, real plan extraction) + GPS presence
    (local, computed on the VM) → one episode: the local projection is 'probable', the cloud one 'prévu' (it may not
    see the GPS); nothing is 'confirmed' until the owner says so in a conversation with W.Alter (real extraction, real
    decision model). DSH is asked before and after."""
    setup()
    from walter_memory import episodic, flows
    z = flows.tz()
    tag = uuid.uuid4().hex[:4]
    sat = (NOW.astimezone(z) - timedelta(days=(NOW.astimezone(z).weekday() - 5) % 7 or 7)).date()
    at = lambda h, m=0, d=0: datetime.combine(sat + timedelta(days=d), datetime.min.time(), z).replace(hour=h, minute=m).astimezone(timezone.utc)  # noqa: E731
    with connection() as conn:   # the contact (as Beeper's identities give it)
        ent = conn.execute("insert into core.entities (entity_type, canonical_name) values ('person', %s) returning entity_id::text",
                           (f"Hani{tag}",)).fetchone()["entity_id"]
        ident = conn.execute("""insert into core.source_identities (source, account, external_id, display_name)
                                values ('beeper', 'e2e', %s, %s) returning identity_id::text""", (f"hani{tag}", f"Hani{tag}")).fetchone()["identity_id"]
        conn.execute("insert into core.identity_links (identity_id, entity_id, method, status) values (%s, %s, 'e2e', 'confirmed')", (ident, ent))
    chat_id = f"!hani{tag}:beeper.local"
    for who, text, t in (("c", "Salut ! On se fait Dune samedi soir au Major Cineplex, séance de 22h ?", at(12, 5, -2)),
                         ("o", "Ok super, je prends les places pour 22h", at(12, 20, -2)),
                         ("c", "Top, à samedi 22h devant le Major !", at(12, 22, -2))):
        events.record_events([{"event_type": "message.received" if who == "c" else "message.sent", "source": "beeper",
                               "source_account": "e2e", "source_id": uuid.uuid4().hex, "thread_id": chat_id,
                               "occurred_at": t, "content": text, "privacy_class": "redacted_cloud",
                               "actor_identity_id": ident if who == "c" else None,
                               "payload": {"chat": {"type": "single", "network": "line", "title": f"Hani{tag}"}}}])
    events.record_events([{"event_type": "calendar.event", "source": "calendar", "source_account": "e2e",
                           "source_id": uuid.uuid4().hex, "occurred_at": at(22), "content": "Cinéma Dune",
                           "privacy_class": "cloud_allowed",
                           "payload": {"event_id": f"dune-{tag}", "calendar_id": "owner@example.invalid",
                                       "start": {"dateTime": at(22).astimezone(z).isoformat()},
                                       "end": {"dateTime": at(23, 59).astimezone(z).isoformat()},
                                       "location": "Major Cineplex", "attendees": []}}])
    for k in range(12):
        gps(13.7301, 100.5801, at(1) + timedelta(minutes=10 * k), wifi=f"Home{tag}")
        gps(13.7301, 100.5801, at(1, d=1) + timedelta(minutes=10 * k), wifi=f"Home{tag}")
    for k in range(17):
        gps(13.7460, 100.5340, at(21, 50) + timedelta(minutes=10 * k), wifi=f"Mall{tag}")
    since = at(0, 0, -3)
    out = {"case": "episode", "flows": flows.tick(since, at(23, 59, 1))}
    out["plans"] = episodic.plans(since, chat=llm.chat, limit=5)
    out["build_1"] = episodic.build(since, at(0, 0, 3))
    loc1, cl1 = episode_view("Dune", True), episode_view("Dune", False)
    q = ("Sans utiliser aucun outil, réponds en une phrase : suis-je allé voir Dune au cinéma samedi soir, et en est-on "
         "sûr ?")
    with Gateway():
        ctx1 = injected(q)
        before = ask_dsh(q)
    # the owner tells W.Alter about it (a real conversation turn, real extraction)
    t = f"e2e-cc-{uuid.uuid4().hex[:6]}"
    say("claude_code", t, "owner", "Au fait, samedi soir j'ai bien vu Dune au Major Cineplex avec Hani, c'était génial.",
        at(11, 0, 1))
    say("claude_code", t, "agent", "Noté, ravi que la séance vous ait plu.", at(11, 1, 1))
    out["extraction"] = extract2.process_thread("claude_code", t, force=True, chat=llm.chat)
    search.index_pending()
    out["build_2"] = episodic.build(since, at(0, 0, 3))
    loc2, cl2 = episode_view("Dune", True), episode_view("Dune", False)
    with Gateway():
        ctx2 = injected(q)
        after = ask_dsh(q)
    out |= {"local_before": loc1, "cloud_before": cl1, "local_after": loc2, "cloud_after": cl2,
            "injected_before": ctx1["text"], "injected_after": ctx2["text"], "dsh_before": before, "dsh_after": after}
    from walter_memory import privacy
    full = privacy.cloud_readable("local_only")   # « oui tout » (2026-11-03): the cloud model sees the GPS presence too
    checks = {"one_episode_local_probable": bool(loc1) and loc1["epistemic"] == "probable" and loc1["privacy_class"] == "local_only",
              "cloud_projection_matches_policy": bool(cl1) and (cl1["epistemic"] == "probable" if full else
                                                               cl1["epistemic"] == "candidate" and cl1["privacy_class"] == "cloud_allowed"),
              "never_confirmed_without_owner": all(v and v["epistemic"] != "confirmed" for v in (loc1, cl1)),
              "confirmed_after_owner_words": bool(cl2) and cl2["epistemic"] == "confirmed" and loc2["epistemic"] == "confirmed",
              "model_hedged_before": not has(before["answer"], "oui, vous") and has(before["answer"], "pas", "non", "prévu",
                                                                                   "confirm", "sûr", "certain"),
              "model_sure_after": has(after["answer"], "oui", "avez vu", "êtes allé", "confirm")}
    out["checks"], out["pass"] = checks, all(checks.values())
    return out


# ───────────────────────────── case 4: a day and a week, then a correction ─────────────────────────────
def case_period() -> dict:
    """Day D-2: the owner sets the Héliotrope beta date (real extraction). Day D-1: he corrects it. The day and the
    week are rebuilt from knowledge and episodes (not from text); after the correction only that path is rebuilt."""
    setup()
    from walter_memory import consolidate, periods, views
    from walter_memory.flows import tz
    z = tz()
    d2 = (NOW - timedelta(days=2)).astimezone(z).date()
    t1, t2 = f"e2e-codex-{uuid.uuid4().hex[:6]}", f"e2e-cc-{uuid.uuid4().hex[:6]}"
    tag = uuid.uuid4().hex[:4]
    at = lambda d, h: datetime.combine(d, datetime.min.time(), z).replace(hour=h).astimezone(timezone.utc)  # noqa: E731
    say("codex", t1, "owner", f"Pour Héliotrope{tag}, on lance la bêta publique le 20 novembre, c'est décidé.", at(d2, 10))
    say("codex", t1, "agent", f"Entendu : bêta publique d'Héliotrope{tag} le 20 novembre.", at(d2, 10) + timedelta(minutes=1))
    x1 = extract2.process_thread("codex", t1, force=True, chat=llm.chat)
    search.index_pending()
    day1, week1 = periods.build("day", d2), periods.build("week", d2)
    other = periods.build("day", d2 - timedelta(days=8))
    read = lambda k, depth="details": views.read({"depth": depth, "key": k, "max_tokens": 6000}).get("content") or ""  # noqa: E731
    day_before, week_before = read(day1["cloud"]["key"]), read(week1["cloud"]["key"], "overview")
    d1 = d2 + timedelta(days=1)
    say("claude_code", t2, "owner", f"Correction : la bêta d'Héliotrope{tag} est repoussée au 27 novembre, pas le 20.", at(d1, 9))
    say("claude_code", t2, "agent", f"Corrigé : bêta d'Héliotrope{tag} le 27 novembre.", at(d1, 9) + timedelta(minutes=1))
    x2 = extract2.process_thread("claude_code", t2, force=True, chat=llm.chat)
    search.index_pending()
    with connection() as conn:
        stale = set(periods.stale_keys(conn))
    rebuilt = periods.tick(days=0)
    periods.build("day", d1)
    day_after, week_after = read(day1["cloud"]["key"]), read(week1["cloud"]["key"], "overview")
    day1_after = read(periods.window("day", d1)[2])
    mine = lambda text, w: [l for l in text.splitlines() if f"Héliotrope{tag}" in l and w in l]  # noqa: E731
    q = (f"Sans utiliser aucun outil, réponds en une phrase : quelle est la date de la bêta d'Héliotrope{tag} et a-t-elle "
         f"changé cette semaine ?")
    with Gateway():
        ctx = injected(q)
        ans = ask_dsh(q)
    checks = {"day_lists_decision": bool(mine(day_before, "20 novembre")),
              "correction_marks_day_and_week_stale": day1["cloud"]["key"] in stale and week1["cloud"]["key"] in stale,
              "other_day_untouched": other["cloud"]["key"] not in stale,
              "day_shows_replaced": any("remplacé" in l for l in mine(day_after, "20 novembre")),
              "next_day_shows_correction": bool(mine(day1_after, "27")),
              "week_shows_the_current_date": "27" in week_after,
              "model_answers_current": has(ans["answer"], "27"),
              }
    return {"case": "period", "extraction": [x1, x2], "stale": sorted(stale), "rebuilt": rebuilt,
            "day_before": day_before, "day_after": day_after, "next_day": day1_after, "week_before": week_before,
            "week_after": week_after, "injected": ctx["text"], "dsh": ans, "checks": checks, "pass": all(checks.values())}


CASES = {"decision": case_decision, "working": case_working, "episode": case_episode, "period": case_period}


def main() -> None:
    require_test_db()
    ap = argparse.ArgumentParser()
    ap.add_argument("case", choices=[*CASES, "all"])
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    results = [CASES[c]() for c in (CASES if a.case == "all" else [a.case])]
    text = json.dumps(results, ensure_ascii=False, indent=1, default=str)
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True)
        (Path(a.out) / f"e2e-{a.case}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json").write_text(text)
    for r in results:
        print(r["case"], "PASS" if r["pass"] else "FAIL", json.dumps(r["checks"]))
        for k in ("with_memory", "control_without_memory"):
            if k in r:
                print(f"  {k}: {r[k]['answer']!r} ({r[k]['seconds']} s)")


if __name__ == "__main__":
    main()
