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
        for line in Path("/opt/walter-memory/.env").read_text().splitlines():   # the gateway token, as the unit loads it
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


def ask_dsh(prompt: str, *, memory: bool = True, timeout: int = 300) -> dict:
    """One real DSH headless turn; its hook injects Walter's context from the TEST gateway (memory=False: control)."""
    ws = tempfile.mkdtemp(prefix="walter-scenario-dsh-e2e-")
    # Only the memory context comes from the test gateway. The run is a production `test` run (walter-llm serves DSH
    # only within an open run and caps a test run's spend); the bench workspace keeps the session out of core.events.
    env = {k: v for k, v in os.environ.items() if k != "WALTER_MEMORY_DATABASE_URL"}
    env |= {"DSH_HOME": "/opt/dsh/home", "WALTER_MEMORY_URL": f"http://127.0.0.1:{PORT}", "WALTER_HOOK_SKILLS": "off",
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


CASES = {"decision": case_decision, "working": case_working}


def main() -> None:
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
