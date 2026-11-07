"""Walter Run Plane (P0, 2026-10-27): runs, tasks and their links, plus the matching bus events.

A run is the handling of one request; its run_id is Walter's canonical identifier, propagated to tools,
sub-agents and Memory. Adapters (walter_hook for each harness, walter-router's sub-agent) call this library;
the projection (runs.*) is written in the same transaction as the bus event, so no extra service is needed.
Writers are fail-open (`safe`) where a harness hook calls them: a run that cannot be recorded never blocks an agent.
"""
from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import connect

GOAL_MAX = 500
ABANDON_AFTER = "24 hours"


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
    return run_id


def end(run_id: str, status: str = "ended", costs: dict | None = None) -> None:
    with connect() as conn:
        row = conn.execute(
            """update runs.runs set status = %s, ended_at = coalesce(ended_at, now()), costs = coalesce(%s, costs),
                      updated_at = now() where run_id = %s and status = 'open' returning started_at, ended_at""",
            (status, json.dumps(costs) if costs else None, run_id)).fetchone()
        if row:
            _emit(conn, "run.ended", run_id, {"run_id": run_id, "status": status,
                                              "seconds": round((row["ended_at"] - row["started_at"]).total_seconds(), 1)},
                  f"run.ended/{run_id}")


def end_open(session_id: str, status: str = "ended") -> str | None:
    """End the latest open run of a harness session (adapters that know the session, not the run: Hermes, Codex)."""
    with connect() as conn:
        row = conn.execute("""select run_id from runs.runs where status = 'open' and origin->>'session_id' = %s
                              order by started_at desc limit 1""", (session_id,)).fetchone()
    if row:
        end(str(row["run_id"]), status)
        return str(row["run_id"])
    return None


REQUESTED_KEYS = ("task", "level", "require", "fast_path", "answer", "message_sha")


def update(run_id: str, *, thread_id: str | None = None, level: str | None = None, act: str | None = None,
           requested: dict | None = None) -> dict:
    """What is learned after the start (preflight). act correct/continue links the run to the run it follows: the
    previous run of the same harness session, else of the same thread (a correction never rewrites its parent).
    `requested` = what the preflight asks of Walter Router for this turn (task, text tier, required capabilities,
    a rule's answer when no model is needed): kept in routing.requested, read by the model gateway (lot 2,
    2026-11-07); the observed route written later keeps it."""
    out = {}
    req = {k: requested[k] for k in REQUESTED_KEYS if isinstance(requested, dict) and requested.get(k) not in (None, "", [])}
    with connect() as conn:
        conn.execute("""update runs.runs set thread_id = coalesce(%s, thread_id), level = coalesce(%s, level),
                        act = coalesce(%s, act), updated_at = now(),
                        routing = case when %s::jsonb is null then routing
                                       else coalesce(routing, '{}'::jsonb) || jsonb_build_object('requested', %s::jsonb) end
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
    """Close runs and tasks that never received an end (session closed, harness killed)."""
    with connect() as conn:
        n = conn.execute(f"""update runs.runs set status = 'abandoned', ended_at = now(), updated_at = now()
                             where status = 'open' and started_at < now() - interval '{ABANDON_AFTER}'""").rowcount
        conn.execute(f"""update runs.tasks set status = 'abandoned', ended_at = now()
                         where status = 'open' and started_at < now() - interval '{ABANDON_AFTER}'""")
    return n


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
