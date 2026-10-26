"""One guardian pass: detect, follow incidents, act, tell the owner only what is worth it.

Actions, cheapest first: a provider seen down is probed again (its status heals by itself when it is back); a
stale source is read again; only what is still broken after that, and repairable on our side, goes to the L2
agent (repair.py). The owner hears about a repair that landed, a decision only he can take, or an outside outage
that lasts; never about routine checks.
"""
from __future__ import annotations

import fcntl
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from walter_router import instance
from walter_router.guardian import checks, repair
from walter_router.store import db

MAX_ATTEMPTS = 3          # agent runs per incident before it is handed to the owner
RETRY_AFTER_H = 12        # between two agent runs on the same incident
TEST_GRACE_H = 6          # a failing test is often someone's work in progress: act only if it lasts
MAX_REPAIRS_PER_PASS = 3
EXTERNAL_NOTICE_H = 48    # an outside outage is worth a message only when it lasts this long

_CLOSED_OK = ("fixed", "resolved")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_h(ts) -> float:
    return (_now() - ts).total_seconds() / 3600 if ts else 1e9


def sync(conn, problems: list[dict], tests_checked: bool) -> list[dict]:
    """Open or refresh one incident per problem; close those no longer seen (a test incident only when the
    tests ran this pass). Returns the open incidents."""
    seen = {p["key"] for p in problems}
    for p in problems:
        conn.execute("""insert into models.guardian_incidents (key, kind, subject, detail) values (%s, %s, %s, %s)
                        on conflict (key) where closed_at is null
                        do update set last_seen_at = now(), detail = excluded.detail, kind = excluded.kind""",
                     (p["key"], p["kind"], p["subject"], json.dumps(p["detail"], default=str)))
    for inc in conn.execute("select * from models.guardian_incidents where closed_at is null").fetchall():
        if inc["key"] in seen or (inc["kind"] == "test_failure" and not tests_checked):
            continue
        status = "fixed" if inc["status"] in ("fixed", "repairing", "deferred") else "resolved"
        conn.execute("update models.guardian_incidents set status = %s, closed_at = now() where incident_id = %s",
                     (status, inc["incident_id"]))
    return conn.execute("select * from models.guardian_incidents where closed_at is null order by opened_at").fetchall()


def _set(conn, inc: dict, status: str, verdict: dict | None = None, attempt: bool = False) -> None:
    conn.execute(f"""update models.guardian_incidents set status = %s, verdict = coalesce(%s, verdict)
                     {", attempts = attempts + 1, last_attempt_at = now()" if attempt else ""}
                     where incident_id = %s""",
                 (status, json.dumps(verdict, default=str) if verdict is not None else None, inc["incident_id"]))
    inc["status"] = status
    if verdict is not None:
        inc["verdict"] = verdict


def reread_source(kind: str) -> dict:
    """The router's own read of one source (writes its snapshot when it works)."""
    proc = subprocess.run(["walter-router", "research", "--source", kind], capture_output=True, text=True, timeout=1200)
    try:
        out = json.loads(proc.stdout).get("sources", {}).get(kind) or {}
    except ValueError:
        out = {"error": (proc.stderr or proc.stdout)[-300:]}
    return {"ok": proc.returncode == 0 and "snapshot_id" in out and "error" not in out, **out}


def _needs_agent(inc: dict) -> bool:
    if inc["attempts"] >= MAX_ATTEMPTS or _age_h(inc["last_attempt_at"]) < RETRY_AFTER_H:
        return False
    if inc["kind"] == "test_failure":
        return _age_h(inc["opened_at"]) >= TEST_GRACE_H
    return True


def commit_message(inc: dict, v: dict) -> str:
    """Subject: which incident; body: the agent's cause and evidence, then who did the work."""
    body = "\n\n".join(x for x in (v.get("cause"), v.get("evidence")) if x)
    return (f'Guardian: incident {inc["incident_id"]} repaired ({inc["kind"]})\n\n{inc["subject"]}\n\n{body}\n\n'
            f'Repaired by the L2 agent ({v.get("model")} via {v.get("provider")}), landed through the guardian gates.')


def _repair(conn, inc: dict, dry_run: bool) -> dict:
    module = repair.workspace(inc["incident_id"])
    if dry_run:
        return {"workspace": str(module), "dry_run": True}
    baseline = checks.run_tests(module)
    _set(conn, inc, "repairing", attempt=True)
    ran = repair.agent(inc, module)
    v = {**ran["verdict"], "model": ran.get("model"), "provider": ran.get("provider"), "agent_ok": ran["ok"],
         "agent_error": ran.get("error"), "workspace": str(module), "at": _now().isoformat()}
    outcome = v.get("outcome")
    if outcome == "fixed":
        g = repair.gates(module, inc, baseline)
        v["gates"] = g
        if not g["ok"]:
            _set(conn, inc, "needs_owner" if inc["attempts"] >= MAX_ATTEMPTS else "open", v)
            return v
        landed = repair.apply(module, g["files"], g.get("deleted") or [], commit_message(inc, v))
        v["apply"] = landed
        if not landed["applied"]:
            _set(conn, inc, "deferred", v)
            return v
        if inc["kind"] in ("source_stale", "source_error"):
            v["reread"] = reread_source(inc["subject"])
        _set(conn, inc, "fixed", v)
    elif outcome == "external":
        _set(conn, inc, "external", v)
    elif outcome == "needs_owner":
        _set(conn, inc, "needs_owner", v)
    else:
        _set(conn, inc, "needs_owner" if inc["attempts"] >= MAX_ATTEMPTS else "open", v)
    return v


def _retry_deferred(conn, inc: dict) -> None:
    """A verified patch waiting for files someone else was editing: land it once they are free."""
    v = inc["verdict"] or {}
    g = v.get("gates") or {}
    module = Path(v.get("workspace") or "")
    if not (module / ".git").exists() or not g.get("files"):
        _set(conn, inc, "open")
        return
    landed = repair.apply(module, g["files"], g.get("deleted") or [], commit_message(inc, v))
    v["apply"] = landed
    if landed["applied"]:
        if inc["kind"] in ("source_stale", "source_error"):
            v["reread"] = reread_source(inc["subject"])
        _set(conn, inc, "fixed", v)
    else:
        _set(conn, inc, "deferred", v)


DOCS_OWNER_AFTER_H = 24   # a reference that cannot be regenerated for a day goes to the owner


def _docs(conn, inc: dict, dry_run: bool) -> None:
    """Generated reference: regenerated mechanically, never by the agent; quiet when it works."""
    if dry_run:
        return None
    res = repair.regenerate_docs(f'Guardian: generated reference regenerated (incident {inc["incident_id"]})\n\n'
                                 + "\n".join((inc["detail"] or {}).get("stale") or []))
    if res.get("applied"):
        return _set(conn, inc, "fixed", {"outcome": "fixed", "quiet": True, "apply": res})
    if res.get("deferred"):
        return _set(conn, inc, "deferred", {"outcome": "deferred", "quiet": True, "apply": res})
    owner = _age_h(inc["opened_at"]) >= DOCS_OWNER_AFTER_H
    _set(conn, inc, "needs_owner" if owner else "open", {
        "outcome": "needs_owner" if owner else "open", "apply": res,
        "summary_fr": "La documentation de référence du Router ne se régénère plus depuis un jour : "
                      f'{str(res.get("error"))[:200]}. Il faut une correction dans le module.'})


def handle(conn, inc: dict, budget: list[int], dry_run: bool = False) -> None:
    kind = inc["kind"]
    if kind == "docs_stale":
        return None if inc["status"] == "needs_owner" else _docs(conn, inc, dry_run)
    if inc["status"] == "deferred":
        return _retry_deferred(conn, inc)
    if kind == "provider_down":
        side = (inc["detail"] or {}).get("side")
        if side == "external":
            return _set(conn, inc, "external")
        if side == "account":
            return _set(conn, inc, "needs_owner", {"outcome": "needs_owner", "cause": inc["detail"].get("probe"),
                                                   "summary_fr": f'Le fournisseur {inc["subject"]} refuse nos appels '
                                                                 f'(clé ou crédit) : {inc["detail"].get("probe")}.'})
    if kind in ("source_stale", "source_error") and inc["attempts"] == 0 and inc["status"] == "open":
        again = reread_source(inc["subject"])
        if again["ok"]:
            return _set(conn, inc, "resolved", {"outcome": "resolved", "reread": again})
        inc["detail"] = {**(inc["detail"] or {}), "reread_error": again.get("error")}
    if inc["status"] in ("external", "needs_owner") or not _needs_agent(inc) or budget[0] <= 0:
        return None
    budget[0] -= 1
    _repair(conn, inc, dry_run)


def _message(inc: dict) -> str | None:
    """What the owner reads, once per outcome; None = nothing worth a message."""
    v = inc.get("verdict") or {}
    head = "🛠 Walter Router"
    if inc["status"] == "fixed" and (v.get("apply") or {}).get("applied") and not v.get("quiet"):
        return f'{head} — réparé tout seul\n\n{v.get("summary_fr") or v.get("cause")}\n\nVérifié avant mise en place.'
    if inc["status"] == "needs_owner":
        q = v.get("question_fr")
        return f'{head} — besoin de vous\n\n{v.get("summary_fr") or inc["subject"]}' + (f"\n\n{q}" if q else "")
    if inc["status"] == "external" and _age_h(inc["opened_at"]) >= EXTERNAL_NOTICE_H:
        return (f'{head} — panne extérieure\n\n{inc["subject"]} ne répond plus correctement depuis '
                f'{_age_h(inc["opened_at"]):.0f} h ({(inc["detail"] or {}).get("probe", "")[:120]}). '
                "Le routeur passe par les autres fournisseurs ; rien à faire de votre côté.")
    return None


def notify(conn, incidents: list[dict], send: bool = True) -> list[str]:
    sent = []
    for inc in incidents:
        if inc.get("notified_status") == inc["status"]:
            continue
        text = _message(inc)
        if not text:
            continue
        if send:
            from walter_router.analysis import telegram
            try:
                telegram.send_with_buttons(text, [])
            except Exception:  # noqa: BLE001 — the next pass tries again
                continue
            v = {**(inc.get("verdict") or {}), "notified_status": inc["status"]}
            conn.execute("update models.guardian_incidents set notified_at = now(), verdict = %s where incident_id = %s",
                         (json.dumps(v, default=str), inc["incident_id"]))
        sent.append(text)
    return sent


def run(agent: bool = True, tests: bool = True, send: bool = True, dry_run: bool = False) -> dict:
    lock = open(instance.state_file("guardian.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return {"skipped": "another guardian pass is running"}
    instance.state_file("guardian").mkdir(parents=True, exist_ok=True)
    with db.connect() as conn:
        conn.autocommit = True
        from walter_router.serve import execution
        for p in checks.providers(conn):        # fresh verdict before deciding anything about a provider
            execution.probe(conn, only=p["subject"])
        problems = checks.detect(conn, with_tests=tests)
        incidents = sync(conn, problems, tests)
        budget = [MAX_REPAIRS_PER_PASS if agent else 0]
        for inc in incidents:
            inc["notified_status"] = (inc.get("verdict") or {}).get("notified_status")
            handle(conn, inc, budget, dry_run)
        messages = notify(conn, [i for i in incidents if i["status"] != "repairing"], send and not dry_run)
        keep = {(i.get("verdict") or {}).get("workspace") for i in incidents if i["status"] == "deferred"}
        repair.prune(keep={k for k in keep if k})
        return {"problems": problems,
                "incidents": [{k: i[k] for k in ("incident_id", "key", "status", "attempts")} for i in incidents],
                "messages": messages}


def status() -> dict:
    with db.connect() as conn:
        rows = conn.execute("""select incident_id, key, kind, status, opened_at, last_seen_at, closed_at, attempts,
                                      verdict->>'cause' as cause, verdict->>'summary_fr' as summary
                               from models.guardian_incidents
                               where closed_at is null or closed_at > now() - interval '7 days'
                               order by opened_at desc""").fetchall()
    return {"open": [r for r in rows if not r["closed_at"]], "closed_7d": [r for r in rows if r["closed_at"]]}
