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

from walter_router import instance, paths
from walter_router.guardian import checks, repair
from walter_router.store import db

MAX_ATTEMPTS = 2          # repair-agent runs per incident before it is handed to the owner (coding/L3 since 20/11)
RETRY_AFTER_H = 5         # between two runs on the same incident: the next pass (every 6 h) tries again
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
    # the same outcome keeps its « already told » mark: rewriting the verdict every pass erased it, so a needs_owner
    # message (Venice without credit, since 14/11) went again every other pass (2026-11-21)
    told = (inc.get("verdict") or {}).get("notified_status") or inc.get("notified_status")
    if verdict is not None and told and status == inc.get("status") == told:
        verdict = {**verdict, "notified_status": told}
    conn.execute(f"""update models.guardian_incidents set status = %s, verdict = coalesce(%s, verdict)
                     {", attempts = attempts + 1, last_attempt_at = now()" if attempt else ""}
                     where incident_id = %s""",
                 (status, json.dumps(verdict, default=str) if verdict is not None else None, inc["incident_id"]))
    inc["status"] = status
    if verdict is not None:
        inc["verdict"] = verdict


def _padlock(conn, inc: dict) -> None:
    """An open padlock not on its #1: the adoption goes through the usual path (a proposal compared with the model in
    use, then `auto_adopt`, then the Router's « changé automatiquement » message), checked again afterwards. A model
    the owner refused is never forced: then he is asked."""
    from walter_router.analysis import alerts, telegram
    d = inc["detail"] or {}
    task, role = inc["subject"], d.get("role") or "default"
    alerts.record(conn, "challenger", task, d["best"],
                  {"pinned": d["in_use"], "boards": {}, "origin": "guardian",
                   "composite": {"challenger": d["best_score"], "pinned": d.get("in_use_score"),
                                 "rank": d["best_rank"], "pinned_rank": d.get("in_use_rank")}},
                  "baseline", role)
    done = alerts.auto_adopt(conn, only_task=task, only_role=role)
    now = conn.execute("select pinned_model_id from models.preferences where task = %s and role = %s",
                       (task, role)).fetchone()
    if done and now and now["pinned_model_id"] == d["best"]:
        telegram.notify_auto(conn, done)
        return _set(conn, inc, "fixed", {"outcome": "fixed", "verified": True, "quiet": True, "adopted": done,
                                          "summary_fr": f"{task} : {d['in_use']} → {d['best']} (n°1 du classement)"})
    return _set(conn, inc, "needs_owner", {
        "outcome": "needs_owner", "cause": "padlock_drift",
        "summary_fr": f"Cadenas ouvert, mais {task} n'est pas sur le n°1 de son classement : {d['in_use']} "
                      f"({d.get('in_use_score')}) au lieu de {d['best']} ({d['best_score']}), et je n'ai pas pu "
                      "changer tout seul (proposition déjà refusée, ou modèle sans route).",
        "question_fr": "Je passe sur le n°1, ou vous gardez le modèle actuel (fermez alors le cadenas) ?"})


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


def _tried(inc: dict) -> str:
    v = inc.get("verdict") or {}
    return f'- tentative précédente : {v.get("outcome")} — {str(v.get("cause") or "")[:300]}' if v.get("outcome") else ""


def still_broken(conn, inc: dict) -> bool:
    """The incident's own check, run again after the agent: its word is never enough."""
    kind, subject = inc["kind"], inc["subject"]
    if kind in ("source_stale", "source_error"):
        return not reread_source(subject)["ok"]
    if kind == "test_failure":
        proc = subprocess.run([str(paths.ROOT / "venv" / "bin" / "python"), "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               subject], cwd=paths.ROOT, capture_output=True, text=True, timeout=900)
        return proc.returncode != 0
    if kind == "provider_down":
        from walter_router.serve import execution
        execution.probe(conn, only=subject)
        return any(p["key"] == inc["key"] for p in checks.providers(conn))
    return any(p["key"] == inc["key"] for p in checks.detect(conn, with_tests=False))


def _repair(conn, inc: dict, dry_run: bool) -> dict:
    """The guardians' common repair agent (walter-guardian repair) on this incident, then its own check again."""
    if dry_run:
        return {"dry_run": True}
    tried = _tried(inc)
    _set(conn, inc, "repairing", attempt=True)
    inc["attempts"] += 1                    # this run counts: its own failure may be the last one allowed
    ran = repair.agent(inc, tried)
    v = {**ran["verdict"], "by": "repair-agent", "poste": ran.get("poste"), "agent_ok": ran["ok"],
         "agent_error": ran.get("error"), "walter_session": ran.get("walter_session"), "at": _now().isoformat()}
    outcome = v.get("outcome")
    if outcome == "fixed":
        v["verified"] = not still_broken(conn, inc)
        if v["verified"]:
            return _set(conn, inc, "fixed", v) or v
        v["outcome"] = "failed"
        v["cause"] = f'{v.get("cause") or ""} (vérification : toujours en panne)'.strip()
    if outcome in ("external", "needs_owner"):
        _set(conn, inc, outcome, v)
    else:
        _set(conn, inc, "needs_owner" if inc["attempts"] >= MAX_ATTEMPTS else "open", v)
    return v


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
    if inc["status"] == "deferred":            # a patch of the former copy-and-gates agent: repaired afresh
        _set(conn, inc, "open")
    if kind == "credit_low":                   # the owner's to top up; said once per step crossed
        d = inc["detail"] or {}
        left = f'{d.get("left_usd", 0):.2f}'.replace(".", ",")
        step = f'{d.get("step_usd", 0):g}'.replace(".", ",")
        return _set(conn, inc, "needs_owner", {
            "outcome": "needs_owner", "cause": f'{inc["subject"]} : {d.get("left_usd")} $',
            "summary_fr": f"Il reste {left} $ sur {inc['subject'].capitalize() if inc['subject'] != 'openrouter' else 'OpenRouter'} "
                          f"(passé sous {step} $). Je continue à l'utiliser jusqu'au dernier centime ; une fois vide, "
                          "les tâches qui passent par lui prennent leurs autres routes, ou échouent si elles n'en ont pas. "
                          "Une recharge évite cela."})
    if kind == "padlock_drift":
        return None if dry_run or inc["status"] == "needs_owner" else _padlock(conn, inc)
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
    if inc["status"] == "open" and inc["attempts"] >= MAX_ATTEMPTS:   # out of agent runs: the owner decides
        return _set(conn, inc, "needs_owner", {**(inc.get("verdict") or {}), "outcome": "needs_owner"})
    if inc["status"] in ("external", "needs_owner") or not _needs_agent(inc) or budget[0] <= 0:
        return None
    budget[0] -= 1
    _repair(conn, inc, dry_run)


def _message(inc: dict) -> str | None:
    """What the owner reads, once per outcome; None = nothing worth a message."""
    v = inc.get("verdict") or {}
    head = "🛠 Walter Router"
    if inc["status"] == "fixed" and (v.get("verified") or (v.get("apply") or {}).get("applied")) and not v.get("quiet"):
        return f'{head} — réparé tout seul\n\n{v.get("summary_fr") or v.get("cause")}\n\nVérifié avant mise en place.'
    if inc["status"] == "needs_owner" and inc["kind"] == "credit_low":
        return f'{head} — crédit bas\n\n{v.get("summary_fr")}'
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
        library = {}
        if not dry_run:                         # the library page follows what moved since the last cycle
            try:
                from walter_router.interface import library as library_page
                library = library_page.follow(conn)
            except Exception as exc:  # noqa: BLE001 — the page never blocks a pass; the next one tries again
                library = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        repair.prune()
        return {"problems": problems,
                "incidents": [{k: i[k] for k in ("incident_id", "key", "status", "attempts")} for i in incidents],
                "messages": messages, "library": library}


def status() -> dict:
    with db.connect() as conn:
        rows = conn.execute("""select incident_id, key, kind, status, opened_at, last_seen_at, closed_at, attempts,
                                      verdict->>'cause' as cause, verdict->>'summary_fr' as summary
                               from models.guardian_incidents
                               where closed_at is null or closed_at > now() - interval '7 days'
                               order by opened_at desc""").fetchall()
    return {"open": [r for r in rows if not r["closed_at"]], "closed_7d": [r for r in rows if r["closed_at"]]}
