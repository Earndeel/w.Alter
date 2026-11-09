"""Observability and memory are separate (cleanup phase 2, Monsieur 2026-11-09).

  walter_logs   the canonical journal of what agents executed: every message, tool call (full arguments) and
                result, any runtime. Core observability, not Memory's to copy.
  core.events   the events and observations useful to memory: what happened in Monsieur's life and work.
  Memory        extraction, consolidation, knowledge and their provenance, built from core.events (and reading
                walter_logs when it needs how a task was done).

A technical event may yield a memorable observation (a decision, a fact about a project); that never justifies
copying the execution trace. Until 2026-11-09 the Hermes and agent-sessions connectors copied every tool call
(`tool.called`) and skill use (`skill.used`) into core.events. Both types are now retired: the write door
(types.validate) refuses them, the connectors no longer produce them, and `retire()` removes the historical copies
that walter_logs holds exactly.

`classify()` pairs every such event with walter_logs, one proof per (source, type), never extrapolated:
  tool.called (hermes)   the state.db tool message it was built from (output_ref state.db:messages:<id>) is the
                         walter_logs `tool/result` with source_ref m<id> in the session of the same profile; its call is
                         the `tool/call` with the same call_id just before it. Checks: tool name, args summary
                         (recomputed with the connector's own historical function), status, output size.
  skill.used (hermes)    the same tool message: tool = action, call args name = skill.
  tool.called (claude_code, codex, dsh)   `tool/result` and `tool/call` with the same session and call_id.
Classes: exact; exact except a secret walter_logs masked at write (core held it in clear); output size measured
differently (walter_logs keeps the whole output, core only a number); duplicate in core of a matched event (Hermes
re-persisted tool messages between July and mid-October: the connector recorded the same call twice under two
message ids; the copy walter_logs never saw has a twin in core with the same payload, same call id, same thread, and
that twin is matched); anything else is a real gap and stays in core.

`retire()` re-runs the proof inside the transaction that deletes, so only what the proof just classified removable
goes. It is a traced Memory operation (system.purges + system.purge_ledger 'operation'), bypasses the append-only
guard only through `walter.purge` for its own transaction, deletes the idempotence keys of what it removes (the
retired type cannot be written again, so no tombstone is needed), emits no bus event (core.events publishes on
insert only) and is idempotent: a second run finds nothing removable and writes nothing.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
from datetime import datetime, timezone

from psycopg.rows import tuple_row

from .db import connect

RETIRED_TYPES = ("tool.called", "skill.used")
OPERATION = "observability.retire"
MASKED = re.compile(r"«secret[^»]*»")
EXACT, EXACT_MASKED = "exact", "exact except secrets masked in walter_logs"
SIZE_ONLY, CORE_TWIN = "differs: output size", "duplicate in core of a matched event"
REMOVABLE = (EXACT, EXACT_MASKED, SIZE_ONLY, CORE_TWIN)


# ── the connectors' historical payload functions, frozen as they built the retired events ──────────────────────
def hermes_args(raw: str | None, limit: int = 300) -> str | None:
    if not raw:
        return None
    try:
        args = json.loads(raw)
        if isinstance(args, dict):
            raw = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)[:120]}" for k, v in args.items())
    except ValueError:
        pass
    return raw[:limit] + ("…" if len(raw) > limit else "")


def hermes_status(content: str | None) -> str | None:
    if not content:
        return None
    head = content[:400].lower()
    if '"error"' in head or '"success": false' in head or '"status": "error"' in head:
        return "error"
    return "ok"


def agent_args(args, limit: int = 300) -> str | None:
    if args in (None, "", {}):
        return None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            pass
    raw = (", ".join(f"{k}={json.dumps(v, ensure_ascii=False)[:120]}" for k, v in args.items())
           if isinstance(args, dict) else str(args))
    return raw[:limit] + ("…" if len(raw) > limit else "")


# ── the proof, event by event ────────────────────────────────────────────────────────────────────────────────────
def classify(conn):
    """Yield (event_id, occurred_at, key, class) for every core event of a retired type. Read-only."""
    cur = conn.cursor(name="obs_hermes", row_factory=tuple_row)
    cur.itersize = 5000
    cur.execute("""
        with c as (
          select e.event_id, e.occurred_at, e.event_type, e.thread_id sid, coalesce(e.payload->>'profile', 'main') prof,
                 e.payload, coalesce(substring(e.payload->>'output_ref' from 'state.db:messages:(\\d+)$'),
                                     substring(e.source_id from 'skill:(\\d+)$')) mid
          from core.events e where e.source = 'hermes' and e.event_type in ('tool.called', 'skill.used'))
        select c.event_id, c.occurred_at, c.event_type, c.sid, c.prof, c.payload, c.mid,
               r.seq is not null, r.tool, r.chars, r.text, k.seq is not null, k.tool, k.text
        from c
        left join walter_logs.sessions s on s.runtime = 'hermes' and s.native_id = c.sid
             and coalesce(s.profile, 'main') = c.prof
        left join walter_logs.events r on r.session_id = s.session_id and r.source_ref = 'm' || c.mid
             and r.type = 'tool/result'
        left join lateral (select seq, tool, text from walter_logs.events k where k.session_id = s.session_id
             and k.type = 'tool/call' and k.call_id = r.call_id and k.seq < r.seq order by k.seq desc limit 1) k
             on true""")
    # every event is kept under its own id (never under its state.db reference alone: one event, one verdict)
    tools, skills = {}, {}
    groups, tool_at, skill_at = (collections.defaultdict(list) for _ in range(3))
    for eid, at, etype, sid, prof, p, mid, has_r, r_tool, r_chars, r_text, has_k, k_tool, k_text in cur:
        key = f"hermes {etype}"
        if mid is None:
            yield eid, at, key, "no state.db reference in core payload"
            continue
        if not has_r:
            cls = "absent from walter_logs"
        elif etype == "skill.used":
            try:
                name = (json.loads(k_text or "") or {}).get("name") if has_k else None
            except ValueError:
                name = None
            tool = k_tool if has_k else r_tool
            if tool == p.get("action") and name == p.get("skill"):
                cls = EXACT
            elif not has_k:
                cls = "call missing in walter_logs (result present)"
            else:
                cls = "differs: " + ", ".join(x for x, ok in (("action", tool == p.get("action")),
                                                               ("skill", name == p.get("skill"))) if not ok)
        else:
            diffs, masked = [], False
            tool = k_tool if has_k and k_tool not in (None, "tool_call") else r_tool
            if tool != p.get("tool"):
                diffs.append("tool name" + (' (walter_logs has generic "tool_call")' if tool in (None, "tool_call")
                                            else ""))
            if (hermes_args(k_text) if has_k else None) != p.get("args_summary"):
                if has_k and MASKED.search(k_text or ""):
                    masked = True
                else:
                    diffs.append("args" if has_k else "args (no call in walter_logs)")
            if (p.get("output_chars") or 0) != (r_chars or 0) and not MASKED.search(r_text or ""):
                diffs.append("output size")
            if p.get("status") != hermes_status(r_text) and not MASKED.search(r_text or ""):
                diffs.append("status")
            cls = (EXACT_MASKED if masked else EXACT) if not diffs else "differs: " + ", ".join(diffs)
        if etype == "skill.used":
            skills[eid] = [eid, at, cls, json.dumps(p, sort_keys=True), (prof, mid)]
            skill_at[(prof, mid)].append(eid)
        else:
            twin_key = (sid, prof, json.dumps({k: v for k, v in p.items() if k != "output_ref"}, sort_keys=True))
            tools[eid] = [eid, at, cls, twin_key, None, (prof, mid)]
            groups[twin_key].append(eid)
            tool_at[(prof, mid)].append(eid)
    cur.close()
    # Hermes re-persisted tool messages: the copy walter_logs never saw has a matched twin in core (same thread,
    # profile and payload but the state.db reference; the payload includes the call id, which makes the twin unique)
    for eid, t in tools.items():
        if t[2] == "absent from walter_logs" and json.loads(t[3][2]).get("call_id"):
            twin = next((x for x in groups[t[3]] if x != eid and tools[x][2] in (EXACT, EXACT_MASKED, SIZE_ONLY)), None)
            if twin:
                t[2], t[4] = CORE_TWIN, twin
        yield t[0], t[1], "hermes tool.called", t[2]
    # a skill use comes from the same tool message: it is a twin when that message's tool.called is one, and the
    # twin message carries exactly one skill use, exact and with the same payload
    for eid, s in skills.items():
        if s[2] == "absent from walter_logs":
            mine = tool_at.get(s[4], [])
            t = tools[mine[0]] if len(mine) == 1 else None
            if t and t[2] == CORE_TWIN:
                other = skill_at.get(tools[t[4]][5], [])
                if len(other) == 1 and skills[other[0]][2] == EXACT and skills[other[0]][3] == s[3]:
                    s[2] = CORE_TWIN
        yield s[0], s[1], "hermes skill.used", s[2]

    cur = conn.cursor(name="obs_agents", row_factory=tuple_row)
    cur.itersize = 5000
    cur.execute("""
        select e.event_id, e.occurred_at, e.source, e.payload, r.seq is not null, r.tool, r.status, r.chars,
               k.seq is not null, k.tool, k.text,
               (select count(*) from walter_logs.events x where x.session_id = s.session_id and x.type = 'tool/result'
                  and x.call_id = e.payload->>'call_id')
        from core.events e
        left join walter_logs.sessions s on s.runtime = e.source and s.native_id = e.payload->>'session_id'
        left join lateral (select seq, tool, status, chars from walter_logs.events r
             where r.session_id = s.session_id and r.type = 'tool/result' and r.call_id = e.payload->>'call_id'
             order by seq limit 1) r on true
        left join lateral (select seq, tool, text from walter_logs.events k where k.session_id = s.session_id
             and k.type = 'tool/call' and k.call_id = e.payload->>'call_id' order by seq limit 1) k on true
        where e.event_type in ('tool.called', 'skill.used') and e.source <> 'hermes'""")
    for eid, at, src, p, has_r, r_tool, r_status, r_chars, has_k, k_tool, k_text, n_res in cur:
        key = f"{src} tool.called"
        if src not in ("claude_code", "codex", "dsh"):
            yield eid, at, f"{src} (no proof for this source)", "unproven source"
            continue
        if not has_r and not has_k:
            yield eid, at, key, "absent from walter_logs"
            continue
        diffs, masked = [], False
        if ((k_tool if has_k else r_tool) or "unknown") != p.get("tool"):
            diffs.append("tool name")
        if (agent_args(k_text) if has_k else None) != p.get("args_summary"):
            if has_k and MASKED.search(k_text or ""):
                masked = True
            else:
                diffs.append("args")
        if not has_r:
            diffs.append("result missing")
        else:
            if (p.get("output_chars") or 0) != (r_chars or 0):
                diffs.append("output size")
            if (p.get("status") or "ok") != (r_status or "ok"):
                diffs.append("status")
        if n_res > 1:
            diffs.append("several results for the call id")
        yield eid, at, key, ((EXACT_MASKED if masked else EXACT) if not diffs else "differs: " + ", ".join(diffs))
    cur.close()


def _conversation_report(conn) -> dict:
    """conversation.started / ended against the walter_logs session (informational: these events stay in core)."""
    report = collections.defaultdict(collections.Counter)
    cur = conn.cursor(name="obs_conv", row_factory=tuple_row)
    cur.execute("""
        select e.source, e.event_type, e.occurred_at, e.payload, s.session_id is not null, s.started_at, s.ended_at,
               s.title, s.model, s.parent_session_id, s.platform, s.cwd, s.meta
        from core.events e
        left join walter_logs.sessions s on s.runtime = e.source and s.native_id = e.thread_id
             and (e.source <> 'hermes' or coalesce(s.profile, 'main') = coalesce(e.payload->>'profile', 'main'))
        where e.event_type in ('conversation.started', 'conversation.ended')""")

    def same_time(a, b):
        return a is not None and b is not None and abs((a - b).total_seconds()) <= 1

    for src, etype, at, p, has_s, s_start, s_end, title, model, parent, platform, cwd, meta in cur:
        key = f"{src} {etype}"
        if not has_s:
            report[key]["absent from walter_logs"] += 1
            continue
        meta, diffs = meta or {}, []
        if etype == "conversation.started":
            if not same_time(at, s_start):
                diffs.append("start time")
            for f, v in {"title": title, "model": model, "parent_session_id": parent, "platform": platform,
                         "cwd": cwd}.items():
                if f in p and (p.get(f) or None) != (v or None):
                    diffs.append(f)
            for f in ("cli_version", "originator", "delegation_depth"):
                if p.get(f) is not None and f not in meta:
                    diffs.append(f"{f} not kept in walter_logs")
        else:
            if not same_time(at, s_end):
                diffs.append("end time")
            for f in ("end_reason", "message_count", "tool_call_count"):
                if p.get(f) is not None and p.get(f) != meta.get(f):
                    diffs.append(f)
            if p.get("cost_usd") is not None and meta.get("estimated_cost_usd") is None:
                diffs.append("cost not kept in walter_logs")
            elif p.get("cost_usd") is not None and abs(float(p["cost_usd"]) - float(meta["estimated_cost_usd"])) > 1e-9:
                diffs.append("cost (core = actual cost when known)")
        report[key]["exact" if not diffs else "differs: " + ", ".join(sorted(set(diffs)))] += 1
    cur.close()
    return {k: dict(v.most_common()) for k, v in report.items()}


def _tally(rows) -> tuple[dict, list]:
    report, removable = collections.defaultdict(collections.Counter), []
    for eid, at, key, cls in rows:
        report[key][cls] += 1
        if cls in REMOVABLE:
            removable.append((eid, at))
    return {k: dict(v.most_common()) for k, v in report.items()}, removable


def _ids_sha(ids) -> str:
    return hashlib.sha256("\n".join(sorted(str(i) for i, _ in ids)).encode()).hexdigest()


def proof(*, conversations: bool = True) -> dict:
    """The read-only proof (one REPEATABLE READ READ ONLY snapshot): counts per (source, type) and class."""
    with connect() as conn:
        conn.execute("set transaction isolation level repeatable read, read only")
        at, snap = conn.execute("select now() at, pg_current_snapshot()::text snap").fetchone().values()
        report, removable = _tally(classify(conn))
        out = {"at": at.isoformat(), "txid_snapshot": snap, "tool": "walter_memory.observability.proof",
               "removable_classes": list(REMOVABLE), "results": report,
               "totals": {k: {"total": sum(v.values()), "removable": sum(n for c, n in v.items() if c in REMOVABLE),
                              "kept": sum(n for c, n in v.items() if c not in REMOVABLE)} for k, v in report.items()},
               "removable_ids_sha256": _ids_sha(removable)}
        if conversations:
            out["conversations (kept in core)"] = _conversation_report(conn)
    return out


def retire(*, requested_by: str, reason: str, execute: bool = False, expect_sha: str | None = None) -> dict:
    """Remove the retired-type events the proof classifies removable, in the proof's own transaction.

    Dry run unless execute (writes nothing). expect_sha: refuse to delete unless the removable set is exactly the one
    a previous dry run reported (removable_ids_sha256). Returns counts only, never content."""
    with connect() as conn:
        conn.execute("set transaction isolation level repeatable read")
        conn.execute("set local lock_timeout = '5s'")
        at = conn.execute("select now() at").fetchone()["at"]
        report, removable = _tally(classify(conn))
        total = conn.execute("select count(*) n from core.events where event_type = any(%s)",
                             (list(RETIRED_TYPES),)).fetchone()["n"]
        classified = sum(sum(v.values()) for v in report.values())
        if classified != total:      # one verdict per event, or nothing is deleted
            conn.rollback()
            return {"operation": OPERATION, "status": f"refused: {classified} verdicts for {total} events",
                    "executed": False}
        sha = _ids_sha(removable)
        kept = {k: sum(n for c, n in v.items() if c not in REMOVABLE) for k, v in report.items()}
        out = {"operation": OPERATION, "at": at.isoformat(), "results": report, "removable": len(removable),
               "kept": kept, "removable_ids_sha256": sha, "executed": False}
        if not execute or not removable:
            out["status"] = "dry_run" if removable else "nothing to remove"
            conn.rollback()
            return out
        if expect_sha and expect_sha != sha:
            conn.rollback()
            return {**out, "status": "refused: the removable set changed since the dry run"}
        conn.execute("set local walter.purge = 'on'")
        conn.execute("create temp table obs_retire (event_id uuid, occurred_at timestamptz) on commit drop")
        with conn.cursor() as cur:
            with cur.copy("copy obs_retire from stdin") as cp:
                for eid, occ in removable:
                    cp.write_row((eid, occ))
        conn.execute("analyze obs_retire")
        n_keys = conn.execute("""delete from core.event_keys k using obs_retire r
                                 where k.event_id = r.event_id and k.event_type = any(%s)""",
                              (list(RETIRED_TYPES),)).rowcount
        n_events = conn.execute("""delete from core.events e using obs_retire r
                                   where e.event_id = r.event_id and e.occurred_at = r.occurred_at
                                     and e.event_type = any(%s)""", (list(RETIRED_TYPES),)).rowcount
        if n_events != len(removable):
            conn.rollback()
            return {**out, "status": f"rolled back: {n_events} deleted for {len(removable)} classified"}
        counts = {"events": n_events, "event_keys": n_keys,
                  "removed": {k: sum(n for c, n in v.items() if c in REMOVABLE) for k, v in report.items()},
                  "kept": kept}
        pid = conn.execute("""insert into system.purges (requested_by, reason, selector, fingerprints, counts, status,
                                  backups_rewritten) values (%s, %s, %s, %s, %s, 'executed', false) returning purge_id""",
                           (requested_by, reason,
                            json.dumps({"operation": OPERATION, "types": list(RETIRED_TYPES),
                                        "removable_classes": list(REMOVABLE), "proof": "walter_memory.observability"}),
                            [sha], json.dumps(counts))).fetchone()["purge_id"]
        conn.execute("""insert into system.purge_ledger (purge_id, kind, target) values (%s, 'operation', %s)
                        on conflict (kind, target) do nothing""", (pid, OPERATION))
        conn.commit()
    from . import purge
    purge.ledger_append({"purge_id": pid, "at": datetime.now(timezone.utc).isoformat(), "kind": "operation",
                         "targets": [OPERATION], "reason_sha256": hashlib.sha256(reason.encode()).hexdigest()})
    return {**out, "executed": True, "status": "executed", "purge_id": pid, "counts": counts}
