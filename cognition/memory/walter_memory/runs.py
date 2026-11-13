"""Walter Run Plane (P0, 2026-10-27): runs, tasks and their links, plus the matching bus events.

A run is the handling of one request; its run_id is Walter's canonical identifier, propagated to tools,
sub-agents and Memory. Adapters (walter_hook for each harness, walter-router's sub-agent) call this library;
the projection (runs.*) is written in the same transaction as the bus event, so no extra service is needed.
Writers are fail-open (`safe`) where a harness hook calls them: a run that cannot be recorded never blocks an agent.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import connect

log = logging.getLogger(__name__)

GOAL_MAX = 500
ABANDON_AFTER = "24 hours"

# ── A3 (socle 2026-11-11): the owner's durable task = runs.tasks kind 'objective' (tunables) ──────────────────────
OBJECTIVE = "objective"
OBJECTIVE_STATUSES = ("open", "suspended", "done", "failed", "cancelled")
ACTIVE = ("open", "suspended")
ATTACH_ACTS = ("continue", "correct", "approve", "validate")   # preflight acts that carry on the thread's objective
REOPEN_ACTS = ("correct",)                 # a correction also re-opens a done / failed objective of the thread
CHAT_TASKS = ("general",)                  # Router tasks of a plain chat / information exchange
ACTIONABLE_LEVELS = ("L2", "L3", "L4")     # a requested text tier from L2 up means real work
TASK_THREAD = "task:"                     # an objective opened outside any known subject is its own thread: `task:<id>`
THREAD_SQL = "coalesce(t.thread_id, 'task:' || t.task_id::text)"   # the thread of an objective, always defined
CANDIDATE_SIM = 0.30                       # message ↔ goal similarity (local embeddings) from which an objective is proposed
CANDIDATE_MAX = 3                          # objectives proposed to the preflight as threads, at most
ATTACH_WINDOW = "14 days"                  # an objective older than this (last activity) is not carried on silently
SUSPEND_AFTER = "3 days"                   # open without activity this long → suspended (never abandoned or deleted)
OUTCOME_STATUSES = ("ok", "failed", "cancelled", "interrupted")
OUTCOME_MESSAGE_MAX = 500


_SCHEMA: tuple[float, bool] = (0.0, False)


def has_tasks_schema(conn=None) -> bool:
    """Migration 037 applied (runs.task_runs + runs.episodes.outcome)? Code shipped before the migration keeps the
    previous behaviour until then (production imports this tree). Cached: True for good, False re-checked each 60 s."""
    global _SCHEMA
    if _SCHEMA[1] or (_SCHEMA[0] and time.monotonic() - _SCHEMA[0] < 60):
        return _SCHEMA[1]
    q = """select (to_regclass('runs.task_runs') is not null) and exists (select 1 from information_schema.columns
               where table_schema = 'runs' and table_name = 'episodes' and column_name = 'outcome') ok"""
    if conn is not None:
        ok = bool(conn.execute(q).fetchone()["ok"])
    else:
        with connect() as c:
            ok = bool(c.execute(q).fetchone()["ok"])
    _SCHEMA = (time.monotonic(), ok)
    return ok


def new_id() -> str:
    """uuid7 (time-ordered): 48-bit ms timestamp, version 7, variant 10, random tail."""
    ms = int(time.time() * 1000)
    raw = bytearray(ms.to_bytes(6, "big") + secrets.token_bytes(10))
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


def _goal(text: str | None, privacy_class: str) -> str | None:
    if not text or privacy_class == "local_only":
        return None
    from .logs import mask
    return mask(text.strip())[:GOAL_MAX]


def _emit(conn, type_: str, subject: str, payload: dict, dedupe_key: str | None = None) -> None:
    conn.execute("""insert into bus.events (type, source, subject, payload, dedupe_key) values (%s, 'runs', %s, %s, %s)
                    on conflict (dedupe_key) do nothing""",
                 (type_, subject, json.dumps(payload, ensure_ascii=False, default=str), dedupe_key))


def start(*, origin: dict, goal: str | None = None, run_id: str | None = None, parent_run_id: str | None = None,
          thread_id: str | None = None, privacy_class: str = "cloud_allowed", dedupe_key: str | None = None,
          started_at: datetime | None = None) -> str:
    """Create a run (idempotent on dedupe_key: the existing run_id is returned)."""
    run_id = run_id or new_id()
    with connect() as conn:
        row = conn.execute(
            """insert into runs.runs (run_id, parent_run_id, thread_id, origin, goal, privacy_class, dedupe_key, started_at)
               values (%s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()))
               on conflict (dedupe_key) do update set updated_at = now()
               returning run_id, (xmax = 0) as created""",
            (run_id, parent_run_id, thread_id, json.dumps(origin, default=str), _goal(goal, privacy_class),
             privacy_class, dedupe_key, started_at)).fetchone()
        run_id = str(row["run_id"])
        if row["created"]:
            _emit(conn, "run.created", run_id, {"run_id": run_id, "origin": origin, "parent_run_id": parent_run_id,
                                                "privacy_class": privacy_class}, f"run.created/{run_id}")
            if origin.get("session_id"):
                conn.execute("insert into runs.links (run_id, kind, ref) values (%s, 'session', %s) on conflict do nothing",
                             (run_id, origin["session_id"]))
            if parent_run_id and has_tasks_schema(conn):   # a delegated run works on its parent's objective
                _inherit(conn, run_id, parent_run_id)
    return run_id


def _outcome(outcome: dict | None) -> dict | None:
    """The runtime's structured end of a run (A4), normalised: known status, error message masked and bounded."""
    if not isinstance(outcome, dict):
        return None
    out: dict[str, Any] = {}
    if outcome.get("status") in OUTCOME_STATUSES:
        out["status"] = outcome["status"]
    err = outcome.get("error")
    if isinstance(err, dict) and (err.get("kind") or err.get("message")):
        from .logs import mask
        out["error"] = {"kind": str(err.get("kind") or "error")[:80],
                        "message": mask(str(err.get("message") or ""))[:OUTCOME_MESSAGE_MAX]}
    elif isinstance(err, str) and err:
        from .logs import mask
        out["error"] = {"kind": "error", "message": mask(err)[:OUTCOME_MESSAGE_MAX]}
    for k in ("steps", "tool_calls", "tool_errors"):
        if isinstance(outcome.get(k), (int, float)) and not isinstance(outcome.get(k), bool):
            out[k] = int(outcome[k])
    return out or None


def end(run_id: str, status: str = "ended", costs: dict | None = None, outcome: dict | None = None) -> None:
    """Close an open run (idempotent: a closed run is never relabelled). `outcome` (A4) = {status: ok | failed |
    cancelled | interrupted, error: {kind, message}, steps, tool_calls, tool_errors}: stored on the run and carried by
    the run.ended bus event, the error message masked and bounded."""
    out = _outcome(outcome)
    with connect() as conn:
        if out is not None and not has_tasks_schema(conn):
            out = None                     # before migration 037: no outcome column, the run still ends
        if out is None:
            row = conn.execute(
                """update runs.runs set status = %s, ended_at = coalesce(ended_at, now()), costs = coalesce(%s, costs),
                          updated_at = now() where run_id = %s and status = 'open' returning started_at, ended_at""",
                (status, json.dumps(costs) if costs else None, run_id)).fetchone()
        else:
            row = conn.execute(
                """update runs.runs set status = %s, ended_at = coalesce(ended_at, now()), costs = coalesce(%s, costs),
                          outcome = %s, updated_at = now() where run_id = %s and status = 'open'
                          returning started_at, ended_at""",
                (status, json.dumps(costs) if costs else None, json.dumps(out, ensure_ascii=False), run_id)).fetchone()
        if row:
            payload = {"run_id": run_id, "status": status,
                       "seconds": round((row["ended_at"] - row["started_at"]).total_seconds(), 1)}
            if out is not None:
                payload["outcome"] = out
            _emit(conn, "run.ended", run_id, payload, f"run.ended/{run_id}")
    if row and out is not None and out.get("status") == "interrupted":
        _suspend_interrupted(run_id, out)


def _suspend_interrupted(run_id: str, out: dict) -> None:
    """A run cut by an interruption (engine restart…) leaves its objective resumable at once: `suspended`, with the
    reason — a fact of the Run Plane, not something to wait for the run's evaluation to say (the episode confirms it
    later). Nothing when the objective is closed or a later attempt already carries it on."""
    try:
        task_id = objective_of_run(run_id)
        cur = task_get(task_id) if task_id else None
        if not cur or cur["status"] != "open":
            return
        with connect() as conn:
            later = conn.execute("""select 1 from runs.task_runs tr join runs.runs r on r.run_id = tr.run_id
                                    where tr.task_id = %s and r.started_at > (select started_at from runs.runs
                                                                               where run_id = %s) limit 1""",
                                 (task_id, run_id)).fetchone()
        if later:
            return
        kind = (out.get("error") or {}).get("kind")
        task_update(task_id, status="suspended", by="run",
                    last_outcome={"status": "interrupted", "reason": kind or "interrupted", "run_id": str(run_id),
                                  "at": datetime.now(timezone.utc).isoformat()})
    except Exception:  # noqa: BLE001 - the run is closed whatever happens to its objective; the episode retries
        log.exception("runs: objective of interrupted run %s not suspended", run_id)


def end_open(session_id: str, status: str = "ended", outcome: dict | None = None) -> str | None:
    """End the latest open run of a harness session (adapters that know the session, not the run: Hermes, Codex)."""
    with connect() as conn:
        row = conn.execute("""select run_id from runs.runs where status = 'open' and origin->>'session_id' = %s
                              order by started_at desc limit 1""", (session_id,)).fetchone()
    if row:
        end(str(row["run_id"]), status, outcome=outcome)
        return str(row["run_id"])
    return None


def supersede(session_id: str, run_id: str, status: str = "cancelled") -> list[str]:
    """A harness session serves one owner message at a time: when a new run starts there, an older run of the same
    session that is still open never got its end (the harness restarted mid-turn and its process record went with it)
    → it is closed now. Without this the session has two open runs and every model call of the new one is refused
    as ambiguous (lot E8, 2026-11-10)."""
    with connect() as conn:
        rows = conn.execute("""select run_id from runs.runs where status = 'open' and origin->>'session_id' = %s
                               and run_id <> %s
                               and started_at < (select started_at from runs.runs where run_id = %s)""",
                            (session_id, run_id, run_id)).fetchall()
    old = [str(r["run_id"]) for r in rows]
    for rid in old:
        end(rid, status)
    return old


# model / provider: a model named by the owner for this run (Engine API delegation, lot E5), set at the start; the
# preflight's plan is merged into it, never erases it
REQUESTED_KEYS = ("task", "level", "require", "fast_path", "answer", "message_sha", "model", "provider", "degraded",
                  "work", "resume")


def update(run_id: str, *, thread_id: str | None = None, level: str | None = None, act: str | None = None,
           requested: dict | None = None) -> dict:
    """What is learned after the start (preflight). act correct/continue links the run to the run it follows: the
    previous run of the same harness session, else of the same thread (a correction never rewrites its parent).
    `requested` = what the preflight asks of Walter Router for this turn (task, text tier, required capabilities,
    a rule's answer when no model is needed): kept in routing.requested, read by the model gateway (lot 2,
    2026-11-07); the observed route written later keeps it.
    A3 (2026-11-11): the owner's objective is opened or carried on here (see _objective_for); the result then holds
    `task_id` and `task` = opened | attached | reopened | linked."""
    out = {}
    req = {k: requested[k] for k in REQUESTED_KEYS if isinstance(requested, dict) and requested.get(k) not in (None, "", [])}
    with connect() as conn:
        conn.execute("""update runs.runs set thread_id = coalesce(%s, thread_id), level = coalesce(%s, level),
                        act = coalesce(%s, act), updated_at = now(),
                        routing = case when %s::jsonb is null then routing
                                       else coalesce(routing, '{}'::jsonb) || jsonb_build_object('requested',
                                            coalesce(routing->'requested', '{}'::jsonb) || %s::jsonb) end
                        where run_id = %s""",
                     (thread_id, level, act, json.dumps(req) if req else None, json.dumps(req) if req else None, run_id))
        if act in ("correct", "continue"):
            run = conn.execute("select * from runs.runs where run_id = %s", (run_id,)).fetchone()
            if run and not run["parent_run_id"]:
                prev = conn.execute(
                    """select run_id from runs.runs where run_id <> %s and started_at < %s
                       and (origin->>'session_id' = %s or (%s::text is not null and thread_id = %s))
                       order by (origin->>'session_id' = %s) desc, started_at desc limit 1""",
                    (run_id, run["started_at"], (run["origin"] or {}).get("session_id"), run["thread_id"],
                     run["thread_id"], (run["origin"] or {}).get("session_id"))).fetchone()
                if prev:
                    parent = str(prev["run_id"])
                    conn.execute("""update runs.runs set parent_run_id = %s, correction = coalesce(correction, %s)
                                    where run_id = %s""",
                                 (parent, json.dumps({"scope": "run"}) if act == "correct" else None, run_id))
                    _emit(conn, "run.corrected" if act == "correct" else "run.continued", run_id,
                          {"run_id": run_id, "parent_run_id": parent})
                    out["parent_run_id"] = parent
        if act and has_tasks_schema(conn):
            out.update(_objective_for(conn, run_id, act))
    return out


def repair_goal(run_id: str, goal: str, reason: str) -> dict:
    """Correct a goal recorded from text the owner did not write (e.g. a runtime notice glued to the prompt, lot 1
    2026-11-07). History is kept: the original goal and the reason go to origin.goal_repairs, a bus event is emitted,
    and the run's episode gets a new version (the old one stays)."""
    with connect() as conn:
        run = conn.execute("select goal, privacy_class from runs.runs where run_id = %s", (run_id,)).fetchone()
        if not run:
            return {"error": "unknown run"}
        new = _goal(goal, run["privacy_class"])
        if new == run["goal"]:
            return {"run_id": run_id, "unchanged": True}
        entry = {"original": run["goal"], "reason": reason, "at": datetime.now(timezone.utc).isoformat()}
        conn.execute("""update runs.runs set goal = %s, updated_at = now(),
                        origin = jsonb_set(origin, '{goal_repairs}', coalesce(origin->'goal_repairs', '[]'::jsonb) || %s::jsonb)
                        where run_id = %s""", (new, json.dumps([entry], ensure_ascii=False), run_id))
        _emit(conn, "run.goal_repaired", run_id, {"run_id": run_id, "reason": reason})
        episodic = conn.execute("select 1 from runs.episodes where run_id = %s limit 1", (run_id,)).fetchone()
    out = {"run_id": run_id, "goal": new}
    if episodic:
        from . import episodes
        out["episode"] = episodes.build(run_id, reason="goal_repaired")
    return out


def routing(run_id: str, decision: dict, task_id: str | None = None) -> None:
    """Record a model decision (`applied` false + `constraint` when the harness keeps its own model)."""
    with connect() as conn:
        if task_id:
            conn.execute("update runs.tasks set routing = %s where task_id = %s", (json.dumps(decision), task_id))
        else:   # what the preflight asked of the Router stays next to the observed route
            conn.execute("""update runs.runs set routing = jsonb_strip_nulls(jsonb_build_object('requested', routing->'requested'))
                                                      || %s::jsonb, updated_at = now() where run_id = %s""",
                         (json.dumps(decision), run_id))
        _emit(conn, "routing.selected", run_id, {"run_id": run_id, "task_id": task_id, **decision})


def task_start(run_id: str, *, kind: str, goal: str | None = None, spec: dict | None = None,
               session_id: str | None = None, task_id: str | None = None, parent_task_id: str | None = None) -> str:
    task_id = task_id or new_id()
    with connect() as conn:
        if not parent_task_id and kind != OBJECTIVE and has_tasks_schema(conn):   # delegated inside a run that works on an objective: its child
            row = conn.execute("""select task_id from runs.task_runs where run_id = %s
                                  order by (role = 'origin') desc, at desc limit 1""", (run_id,)).fetchone()
            parent_task_id = str(row["task_id"]) if row else None
        conn.execute("""insert into runs.tasks (task_id, run_id, parent_task_id, kind, goal, spec, session_id, started_at)
                        values (%s, %s, %s, %s, %s, %s, %s, now()) on conflict (task_id) do nothing""",
                     (task_id, run_id, parent_task_id, kind, _goal(goal, "cloud_allowed"),
                      json.dumps(spec or {}, default=str), session_id))
        if session_id:
            conn.execute("insert into runs.links (run_id, kind, ref) values (%s, 'session', %s) on conflict do nothing",
                         (run_id, session_id))
        _emit(conn, "task.started", run_id, {"run_id": run_id, "task_id": task_id, "kind": kind}, f"task.started/{task_id}")
    return task_id


def task_end(task_id: str, *, status: str = "ended", result: dict | None = None) -> None:
    with connect() as conn:
        row = conn.execute("""update runs.tasks set status = %s, result = %s, ended_at = now()
                              where task_id = %s and status = 'open' returning run_id""",
                           (status, json.dumps(result or {}, default=str), task_id)).fetchone()
        if row:
            _emit(conn, "task.ended", str(row["run_id"]), {"run_id": str(row["run_id"]), "task_id": task_id,
                                                          "status": status}, f"task.ended/{task_id}")


def trace(session_id: str, events: list[dict], *, runtime: str, native_id: str, model: str | None = None,
          parent_session_id: str | None = None, title: str | None = None, meta: dict | None = None) -> int:
    """Write a sub-agent's own trace as a walter_logs session (masked at write, idempotent on event identity).
    events: [{type, at, text, tool, call_id, model, status}] in order; types are walter_logs' vocabulary."""
    from .logs import Writer

    def at(v):
        if isinstance(v, str):
            v = datetime.fromisoformat(v)
        return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)
    events = [{**ev, "at": at(ev.get("at"))} for ev in events]
    with connect() as conn:
        w = Writer(conn)
        w.session(session_id, runtime=runtime, native_id=native_id, model=model, title=title,
                  parent_session_id=parent_session_id, meta=meta or {},
                  started_at=events[0].get("at") if events else None, ended_at=events[-1].get("at") if events else None)
        for i, ev in enumerate(events):
            w.add(session_id, ev["type"], ev.get("at"), f"{native_id}:{i}", text=ev.get("text"), call_id=ev.get("call_id"),
                  tool=ev.get("tool"), model=ev.get("model"), status=ev.get("status"),
                  human=ev["type"] == "user/message")
        return w.flush()


def link(run_id: str, kind: str, ref: str) -> None:
    with connect() as conn:
        conn.execute("insert into runs.links (run_id, kind, ref) values (%s, %s, %s) on conflict do nothing",
                     (run_id, kind, ref))


def sweep() -> int:
    """Close runs and delegated sub-tasks that never received an end (session closed, harness killed), and suspend
    objectives idle for SUSPEND_AFTER (an objective is never abandoned: it stays findable). Returns the runs closed.
    Callers: walter_hook.run_start (1 start in 50), `walter-memory runs sweep`, `walter-memory tasks sweep`."""
    with connect() as conn:
        n = conn.execute(f"""update runs.runs set status = 'abandoned', ended_at = now(), updated_at = now()
                             where status = 'open' and started_at < now() - interval '{ABANDON_AFTER}'""").rowcount
        conn.execute(f"""update runs.tasks set status = 'abandoned', ended_at = now()
                         where status = 'open' and kind <> '{OBJECTIVE}'
                           and started_at < now() - interval '{ABANDON_AFTER}'""")
    suspend_idle()
    return n


def suspend_idle() -> list[str]:
    """Objectives open without activity for SUSPEND_AFTER → suspended (a continuation of the thread re-opens them)."""
    if not has_tasks_schema():
        return []
    with connect() as conn:
        rows = conn.execute(f"""update runs.tasks set status = 'suspended', updated_at = now()
                                where kind = '{OBJECTIVE}' and status = 'open'
                                  and coalesce(updated_at, started_at) < now() - interval '{SUSPEND_AFTER}'
                                returning task_id, run_id, thread_id""").fetchall()
        for r in rows:
            _emit(conn, "task.updated", str(r["run_id"]),
                  {"task_id": str(r["task_id"]), "thread_id": r["thread_id"], "status": "suspended",
                   "old_status": "open", "reason": "idle"}, f"task.updated/{r['task_id']}/suspended/{new_id()}")
    return [str(r["task_id"]) for r in rows]


# ── A3: objectives ────────────────────────────────────────────────────────────────────────────────────────────────

def actionable(requested: dict | None) -> bool:
    """Is a new request real work (→ an objective) rather than a chat or a question? The preflight's own judgement
    (`work`) when it gave one; a degraded plan judged nothing and opens nothing; without either (older caller), from
    what it asks of the Router: not answered
    by a rule / fast path, and either a text tier from L2 up, a Router task other than a plain chat (CHAT_TASKS), or
    tools required."""
    r = requested if isinstance(requested, dict) else {}
    if r.get("fast_path") or r.get("answer"):
        return False
    if r.get("degraded") is True:           # a plan made without its model judged nothing: its prudent profile (a
        return False                        # high tier, tools) is not a judgement that the message is work to carry
        #   through — every message of an outage opened a task under its own words (13/11/2026). An open task of the
        #   thread is still carried on (ATTACH_ACTS); a new one waits for a plan that judged.
    if isinstance(r.get("work"), bool):     # the preflight judged it (2026-11-12): its answer, not the proxy below
        return r["work"]
    require = r.get("require") or []
    return (r.get("level") in ACTIONABLE_LEVELS or (r.get("task") or "general") not in CHAT_TASKS
            or (isinstance(require, (list, tuple)) and "tools" in require))


def _objective_id(run_id: str) -> str:
    """One objective per opening run (idempotent: the preflight may attach its plan twice)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"walter:objective/{run_id}"))


def _inherit(conn, run_id: str, parent_run_id: str) -> None:
    conn.execute("""insert into runs.task_runs (task_id, run_id, role)
                    select task_id, %s, 'attempt' from runs.task_runs where run_id = %s
                    order by (role = 'origin') desc, at desc limit 1
                    on conflict do nothing""", (run_id, parent_run_id))


def _session_match(column: str = "r.origin->>'session_id'") -> str:
    """SQL matching a harness session given whole (dsh/vm/x) or by its native id (x)."""
    return f"({column} = %s or {column} like '%%/' || %s)"


def _objective_for(conn, run_id: str, act: str) -> dict:
    """Open or carry on the owner's objective when the preflight attaches its plan (A3).
      act = new and the request is actionable (actionable())            → a new objective, origin = this run
      act in ATTACH_ACTS                                                  → this run becomes an attempt of the most
          recent objective of the same thread still open or suspended (a suspended one re-opens; a correction also
          re-opens a done / failed one), last active within ATTACH_WINDOW; none and actionable → a new objective
      the plan says `resume` (requested.resume), whatever the act        → same as ATTACH_ACTS
      channel machine (sub-agents)                                        → never opens: inherits through parent_run_id
    Without a thread the same harness session stands in for it. Idempotent per run."""
    run = conn.execute("""select run_id, thread_id, goal, privacy_class, origin, parent_run_id, routing->'requested' req
                          from runs.runs where run_id = %s""", (run_id,)).fetchone()
    if not run:
        return {}
    have = conn.execute("select task_id, role from runs.task_runs where run_id = %s order by (role = 'origin') desc limit 1",
                        (run_id,)).fetchone()
    if have:
        return {"task_id": str(have["task_id"]), "task": "linked"}
    origin = run["origin"] or {}
    if origin.get("channel") == "machine":
        if run["parent_run_id"]:
            _inherit(conn, run_id, str(run["parent_run_id"]))
        return {}
    req = run["req"] or {}
    own = bool(run["thread_id"]) and str(run["thread_id"]).startswith(TASK_THREAD)   # the preflight chose the task itself
    resume = req.get("resume") is True         # … or judged that the message carries on the thread's task (13/11): a
    #   resumption from another session or interface has no previous exchange there, its act is « new »
    if act in ATTACH_ACTS or own or resume:
        statuses = list(ACTIVE) + (["done", "failed"] if act in REOPEN_ACTS else [])
        sid = origin.get("session_id")
        if run["thread_id"]:
            where, args = f"{THREAD_SQL} = %s", [run["thread_id"]]
        elif sid:
            where = f"""exists (select 1 from runs.task_runs tr join runs.runs r on r.run_id = tr.run_id
                               where tr.task_id = t.task_id and {_session_match()})"""
            args = [sid, sid]
        else:
            where, args = None, []
        if where:
            prev = conn.execute(f"""select t.task_id, t.status, {THREAD_SQL} thread from runs.tasks t
                                    where t.kind = '{OBJECTIVE}' and t.status = any(%s) and {where}
                                      and coalesce(t.updated_at, t.started_at) > now() - interval '{ATTACH_WINDOW}'
                                    order by coalesce(t.updated_at, t.started_at) desc limit 1""",
                                [statuses] + args).fetchone()
            if prev:
                tid = str(prev["task_id"])
                conn.execute("insert into runs.task_runs (task_id, run_id, role) values (%s, %s, 'attempt') on conflict do nothing",
                             (tid, run_id))
                conn.execute("""update runs.tasks set status = 'open', ended_at = null, updated_at = now()
                                where task_id = %s""", (tid,))
                conn.execute("update runs.runs set thread_id = %s where run_id = %s and thread_id is null",
                             (prev["thread"], run_id))      # a run that works on an objective carries its thread
                how = "attached" if prev["status"] == "open" else "reopened"
                _emit(conn, "task.updated", run_id, {"task_id": tid, "run_id": run_id, "thread_id": prev["thread"],
                                                     "status": "open", "old_status": prev["status"], "reason": how,
                                                     "act": act}, f"task.updated/{tid}/attempt/{run_id}")
                return {"task_id": tid, "task": how}
    if act not in ("new",) + ATTACH_ACTS or not actionable(req):
        return {}
    tid = _objective_id(run_id)
    if own:                                    # the task of that thread is closed: the new request gets its own
        thread = TASK_THREAD + tid
        conn.execute("update runs.runs set thread_id = %s where run_id = %s", (thread, run_id))
    else:
        thread = run["thread_id"] or TASK_THREAD + tid
        conn.execute("update runs.runs set thread_id = %s where run_id = %s and thread_id is null", (thread, run_id))
    row = conn.execute(f"""insert into runs.tasks (task_id, run_id, kind, goal, spec, session_id, thread_id, progress,
                                                   started_at, updated_at)
                           values (%s, %s, '{OBJECTIVE}', %s, %s, %s, %s, '{{}}'::jsonb, now(), now())
                           on conflict (task_id) do nothing returning task_id""",
                       (tid, run_id, run["goal"], json.dumps({"act": act, "requested": req}, default=str),
                        origin.get("session_id"), thread)).fetchone()
    conn.execute("insert into runs.task_runs (task_id, run_id, role) values (%s, %s, 'origin') on conflict do nothing",
                 (tid, run_id))
    if row:
        _emit(conn, "task.opened", run_id, {"task_id": tid, "run_id": run_id, "thread_id": thread,
                                            "act": act, "task": req.get("task"), "level": req.get("level")},
              f"task.opened/{tid}")
    return {"task_id": tid, "task": "opened"}


def _last_outcome_text(lo: dict | None) -> str | None:
    if not lo:
        return None
    reason = lo.get("reason")
    return (f"{lo.get('status')}: {reason}" if reason else str(lo.get("status")))[:200]


def _task_shape(r: dict) -> dict:
    return {"task_id": str(r["task_id"]), "goal": r["goal"], "status": r["status"], "thread_id": r["thread_id"],
            "updated_at": (r["updated_at"] or r["started_at"]).isoformat(), "progress": r["progress"] or {},
            "attempts": int(r["attempts"] or 0), "last_outcome": _last_outcome_text(r["last_outcome"])}


TASK_SELECT = f"""select t.task_id, t.goal, t.status, {THREAD_SQL} thread_id, t.updated_at, t.started_at, t.progress, t.last_outcome,
                        t.result, t.run_id, (select count(*) from runs.task_runs tr where tr.task_id = t.task_id) attempts
                 from runs.tasks t"""


def tasks_list(thread_id: str | None = None, session_id: str | None = None, status: str | list | None = None,
               limit: int = 10, channels: list[str] | None = None) -> list[dict]:
    """The owner's objectives, most recently active first, in the binding shape (SOCLE.md, contracts between lots):
    {task_id, goal, status, thread_id, updated_at, progress, attempts, last_outcome}. status: one status, a list, 'all',
    or None = the active ones (open, suspended). session_id (whole or native id): objectives worked on in that harness
    session or belonging to a thread it worked on. channels: only objectives opened by runs of these channels (the
    Context board shows the owner's, never a bench's)."""
    if not has_tasks_schema():
        return []
    where, args = [f"t.kind = '{OBJECTIVE}'"], []
    if channels:
        where.append("""exists (select 1 from runs.runs o where o.run_id = t.run_id
                                and coalesce(o.origin->>'channel', 'owner') = any(%s))""")
        args.append(list(channels))
    if status != "all":
        where.append("t.status = any(%s)")
        args.append([status] if isinstance(status, str) else list(status or ACTIVE))
    if thread_id:
        where.append(f"{THREAD_SQL} = %s"); args.append(thread_id)
    if session_id:
        where.append(f"""({THREAD_SQL} in (select r.thread_id from runs.runs r where {_session_match()}
                                          and r.thread_id is not null)
                          or exists (select 1 from runs.task_runs tr join runs.runs r on r.run_id = tr.run_id
                                     where tr.task_id = t.task_id and {_session_match()}))""")
        args += [session_id, session_id, session_id, session_id]
    with connect() as conn:
        rows = conn.execute(f"""{TASK_SELECT} where {' and '.join(where)}
                                order by coalesce(t.updated_at, t.started_at) desc limit %s""",
                            args + [max(1, min(int(limit or 10), 100))]).fetchall()
    return [_task_shape(r) for r in rows]


def objective_candidates(message: str, session_id: str | None = None, at: datetime | None = None, embed=None,
                         exclude: set | frozenset = frozenset()) -> dict:
    """The owner's active objectives a new message may carry on, as thread cards for the preflight (A3: the task
    follows its thread, not the session — a new session or another interface finds it here). Proposed: the objective
    the session's last owner run worked on and those whose goal is close to the message (local embeddings,
    CANDIDATE_SIM), at most CANDIDATE_MAX. 'waiting' = the thread of the session's last owner run (its objective's,
    else the run's own): a short reply, an approval, a correction belong to it. Nothing leaves the VM here."""
    empty = {"candidates": [], "waiting": None, "waiting_age_s": None}
    if not has_tasks_schema():
        return empty
    at = at or now()
    with connect() as conn:
        rows = conn.execute(f"""
            select t.task_id::text, t.goal, t.status, {THREAD_SQL} thread, t.progress, t.last_outcome,
                   coalesce(t.updated_at, t.started_at) last_at
            from runs.tasks t join runs.runs o on o.run_id = t.run_id
            where t.kind = '{OBJECTIVE}' and t.status = any(%s) and t.goal is not null
              and coalesce(o.origin->>'channel', 'owner') = 'owner' and o.privacy_class <> 'local_only'
              and coalesce(t.updated_at, t.started_at) > %s - interval '{ATTACH_WINDOW}'
            order by coalesce(t.updated_at, t.started_at) desc limit 20""", (list(ACTIVE), at)).fetchall()
        last = conn.execute(f"""
            select r.run_id, r.thread_id, coalesce(r.ended_at, r.started_at) at,
                   (select tr.task_id::text from runs.task_runs tr where tr.run_id = r.run_id limit 1) task_id
            from runs.runs r where {_session_match()} and coalesce(r.origin->>'channel', 'owner') = 'owner'
              and r.started_at < %s
              and not (r.status = 'open' and r.act is null and r.level is null and r.thread_id is null)
            order by r.started_at desc limit 1""",
            (session_id, session_id, at)).fetchone() if session_id else None
        # ^ the run of the message being planned is already open when the preflight asks (the engine opens the run,
        #   then plans it): it has no plan yet, and it is not « the last exchange » (found on the live engine,
        #   2026-11-12: 'waiting' was always empty there, the unit tests had no run in progress)
    # the thread the session's last exchange went to, as the Run Plane recorded it (the plan's thread, or the
    # objective's): known at once, where Memory attaches a subject to an exchange only after it
    went = ({"waiting": last["thread_id"], "waiting_age_s": max(0.0, (at - last["at"]).total_seconds())}
            if last and last["thread_id"] else {"waiting": None, "waiting_age_s": None})
    if not rows:
        return {"candidates": [], **went}
    waiting = next((r for r in rows if last and r["task_id"] == last["task_id"]), None)
    sims = {}
    if (message or "").strip():
        if embed is None:
            from .search import embed
        try:
            vs = embed([message[:1500]] + [r["goal"][:1500] for r in rows])
            norm = lambda v: sum(x * x for x in v) ** 0.5 or 1.0                      # noqa: E731
            q, qn = vs[0], norm(vs[0])
            sims = {r["task_id"]: sum(a * b for a, b in zip(q, v)) / (qn * norm(v)) for r, v in zip(rows, vs[1:])}
        except Exception:  # noqa: BLE001 — without embeddings only the session's own objective is proposed
            sims = {}
    keep = [r for r in rows if r is waiting or sims.get(r["task_id"], 0) >= CANDIDATE_SIM]
    keep.sort(key=lambda r: (r is not waiting, -sims.get(r["task_id"], 0)))
    cards = []
    for r in keep:
        if r["thread"] in exclude or len(cards) >= CANDIDATE_MAX:
            continue
        state = {"open": "tâche ouverte", "suspended": "tâche suspendue (interrompue ou sans activité)"}[r["status"]]
        if r["progress"]:
            state += " ; progrès : " + " ".join(json.dumps(r["progress"], ensure_ascii=False, default=str).split())[:200]
        outcome = _last_outcome_text(r["last_outcome"])
        if outcome:
            state += " ; dernier résultat : " + outcome[:200]
        goal = " ".join(r["goal"].split())
        cards.append({"id": r["thread"], "kind": "task", "title": goal[:100], "objective": goal[:300], "state": state,
                      "hours_since_last": round((at - r["last_at"]).total_seconds() / 3600, 1),
                      "similarity": round(float(sims[r["task_id"]]), 3) if r["task_id"] in sims else None})
    if waiting:
        went = {"waiting": waiting["thread"], "waiting_age_s": max(0.0, (at - last["at"]).total_seconds())}
    return {"candidates": cards, **went}


def task_get(task_id: str) -> dict | None:
    if not has_tasks_schema():
        return None
    with connect() as conn:
        r = conn.execute(f"{TASK_SELECT} where t.task_id::text = %s and t.kind = '{OBJECTIVE}'", (str(task_id),)).fetchone()
    return _task_shape(r) | {"result": r["result"] or {}} if r else None


def objective_of_run(run_id: str) -> str | None:
    if not has_tasks_schema():
        return None
    with connect() as conn:
        r = conn.execute("""select task_id from runs.task_runs where run_id = %s
                            order by (role = 'origin') desc, at desc limit 1""", (run_id,)).fetchone()
    return str(r["task_id"]) if r else None


NOTES_MAX = 20


def task_update(task_id: str, status: str | None = None, progress: dict | None = None, result: dict | None = None,
                note: str | None = None, *, last_outcome: dict | None = None, by: str = "api") -> dict:
    """Update an objective (the engine's task_state tool, the run episode, the owner). progress / result are merged
    key by key into what is there; a note is appended to progress.notes (masked, bounded). Status: open | suspended |
    done | failed | cancelled (done / failed / cancelled set ended_at; open clears it). Emits task.updated."""
    if status is not None and status not in OBJECTIVE_STATUSES:
        return {"error": f"unknown status {status!r}"}
    if not has_tasks_schema():
        return {"error": "tasks schema not migrated (037)"}
    from .logs import mask
    prog = dict(progress) if isinstance(progress, dict) else {}
    with connect() as conn:
        cur = conn.execute(f"select status, progress, run_id, thread_id from runs.tasks where task_id::text = %s and kind = '{OBJECTIVE}'",
                           (str(task_id),)).fetchone()
        if not cur:
            return {"error": "unknown task"}
        if note:
            notes = list(((cur["progress"] or {}).get("notes")) or [])
            notes.append({"at": now().isoformat(), "note": mask(str(note))[:300], "by": by})
            prog["notes"] = notes[-NOTES_MAX:]
        conn.execute("""update runs.tasks set status = coalesce(%s, status),
                               ended_at = case when %s in ('done', 'failed', 'cancelled') then coalesce(ended_at, now())
                                               when %s in ('open', 'suspended') then null else ended_at end,
                               progress = case when %s::jsonb is null then progress
                                               else coalesce(progress, '{}'::jsonb) || %s::jsonb end,
                               result = case when %s::jsonb is null then result
                                             else coalesce(result, '{}'::jsonb) || %s::jsonb end,
                               last_outcome = coalesce(%s::jsonb, last_outcome), updated_at = now()
                        where task_id::text = %s""",
                     (status, status, status, json.dumps(prog, ensure_ascii=False, default=str) if prog else None,
                      json.dumps(prog, ensure_ascii=False, default=str) if prog else None,
                      json.dumps(result, ensure_ascii=False, default=str) if result else None,
                      json.dumps(result, ensure_ascii=False, default=str) if result else None,
                      json.dumps(last_outcome, ensure_ascii=False, default=str) if last_outcome else None, str(task_id)))
        payload = {"task_id": str(task_id), "thread_id": cur["thread_id"], "status": status or cur["status"],
                   "old_status": cur["status"], "by": by,
                   "changed": [k for k, v in (("progress", prog), ("result", result), ("last_outcome", last_outcome)) if v]}
        _emit(conn, "task.updated", str(cur["run_id"]), payload, f"task.updated/{task_id}/{new_id()}")
    return task_get(str(task_id)) or {"error": "unknown task"}


def show(run_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        run = conn.execute("select * from runs.runs where run_id = %s", (run_id,)).fetchone()
        if not run:
            return None
        tasks = conn.execute("select * from runs.tasks where run_id = %s order by started_at", (run_id,)).fetchall()
        links = conn.execute("select kind, ref, at from runs.links where run_id = %s order by at", (run_id,)).fetchall()
        calls = conn.execute("""select task, model_id, provider, ok, seconds, cost_usd, task_id, usage, cost_status from models.exec_log
                                where run_id = %s order by at""", (run_id,)).fetchall() if _has_exec_run(conn) else []
        children = conn.execute("select run_id, status, goal from runs.runs where parent_run_id = %s", (run_id,)).fetchall()
    return {"run": run, "tasks": tasks, "links": links, "model_calls": calls, "children": children}


def recent(limit: int = 20) -> list[dict]:
    with connect() as conn:
        return conn.execute("""select r.run_id, r.status, r.origin->>'runtime' runtime, r.level, r.started_at,
                                      extract(epoch from (coalesce(r.ended_at, now()) - r.started_at))::int seconds,
                                      (select count(*) from runs.tasks t where t.run_id = r.run_id) tasks, left(r.goal, 80) goal
                               from runs.runs r order by r.started_at desc limit %s""", (limit,)).fetchall()


def _has_exec_run(conn) -> bool:
    return bool(conn.execute("""select 1 from information_schema.columns
                                where table_schema = 'models' and table_name = 'exec_log' and column_name = 'run_id'""").fetchone())


def safe(fn, *args, **kwargs):
    """Fail-open wrapper for hook adapters: returns None instead of raising."""
    if os.environ.get("WALTER_RUNS", "on") == "off":
        return None
    try:
        return fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 — a run that cannot be recorded never blocks an agent
        return None


def now() -> datetime:
    return datetime.now(timezone.utc)
