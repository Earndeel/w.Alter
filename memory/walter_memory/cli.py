"""walter-memory CLI: stats, events, types, objects, jobs, purge."""
from __future__ import annotations

import argparse
import json
import sys

from . import events, ingestion, objects, purge, types
from .db import connection


def _print(obj) -> None:
    print(json.dumps(obj, default=str, ensure_ascii=False, indent=1))


def cmd_stats(_a) -> None:
    with connection() as conn:
        _print({
            "events": conn.execute("select source, count(*) n, max(occurred_at) last from core.events group by 1 order by 1").fetchall(),
            "objects": objects.stats(),
            "identities": conn.execute("select source, account, count(*) n from core.source_identities group by 1,2 order by 1,2").fetchall(),
            "derived": conn.execute("select kind, status, count(*) n from core.derived_items group by 1,2 order by 1,2").fetchall(),
            "connectors": conn.execute("""select c.connector, c.enabled, c.last_success_at, c.last_error_at,
                                                 (select count(*) from ingestion.failures f where f.connector = c.connector and resolved_at is null) open_failures
                                          from ingestion.connectors c order by 1""").fetchall(),
            "jobs": conn.execute("select queue, status, count(*) n from ingestion.jobs group by 1,2 order by 1,2").fetchall(),
            "privacy": conn.execute("select category, count(*) n from privacy.detections where reviewed_at is null group by 1").fetchall(),
        })


def _agent_sessions(args) -> None:
    import importlib.util
    import sys
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "connectors" / "agent_sessions.py"
    spec = importlib.util.spec_from_file_location("walter_memory_agent_sessions", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.argv = ["walter-memory agent-sessions", *args]
    raise SystemExit(module.main())


def main(argv=None) -> None:
    import sys
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["agent-sessions"]:   # the connector parses its own options
        _agent_sessions(argv[1:])
    p = argparse.ArgumentParser(prog="walter-memory", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    sub.add_parser("agent-memory", help="runtime-neutral memory API; versioned JSON request on stdin")
    sub.add_parser("agent-sessions", help="ingest Claude Code / Codex / DSH transcripts (called by runtime hooks)")
    e = sub.add_parser("events"); e.add_argument("--source"); e.add_argument("--type", action="append")
    e.add_argument("--cloud-safe", action="store_true", help="only cloud_allowed canonical events")
    e.add_argument("--thread"); e.add_argument("--since"); e.add_argument("--text"); e.add_argument("--limit", type=int, default=20)
    t = sub.add_parser("types"); t.add_argument("action", choices=["list", "sync"])
    o = sub.add_parser("objects"); o.add_argument("action", choices=["search", "get", "put", "stats"])
    o.add_argument("ref", nargs="?"); o.add_argument("--dest"); o.add_argument("--source", default="vault")
    o.add_argument("--kind"); o.add_argument("--link", action="append", default=[]); o.add_argument("--captured")
    o.add_argument("--privacy", choices=["local_only", "redacted_cloud", "cloud_allowed"])
    o.add_argument("--limit", type=int, default=20)
    o.add_argument("--cloud-safe", action="store_true", help="only cloud_allowed object metadata and bytes")
    o.add_argument("--dest-dir", help="download directory (created only after privacy authorization)")
    n = sub.add_parser("note", help="record a note.recorded event (a statement an agent was told)")
    n.add_argument("content"); n.add_argument("--source", default="claude"); n.add_argument("--context", default="")
    n.add_argument("--tag", action="append", default=[])
    ix = sub.add_parser("index", help="index new canonical rows into search.chunks")
    ix.add_argument("--loops", type=int, default=1000)
    ix.add_argument("--hide-noise", action="store_true", help="recompute recall noise on every indexed event (after a rule change)")
    sq = sub.add_parser("search", help="unified search (FTS + vectors + filters)")
    sq.add_argument("query"); sq.add_argument("--limit", type=int, default=10); sq.add_argument("--source", action="append")
    sq.add_argument("--label", action="append"); sq.add_argument("--since"); sq.add_argument("--until")
    sq.add_argument("--no-derived", action="store_true"); sq.add_argument("--rerank", action="store_true")
    sq.add_argument("--cloud-safe", action="store_true", help="only rows allowed to leave the VM")
    so = sub.add_parser("social", help="P4: resolve identities, groups, baselines, deviations; person cards")
    so.add_argument("action", choices=["refresh", "person", "deviations"]); so.add_argument("query", nargs="?")
    so.add_argument("--cloud-safe", action="store_true")
    cx = sub.add_parser("context", help="P6: assemble the memory context for a query")
    cx.add_argument("query"); cx.add_argument("--no-profile", action="store_true"); cx.add_argument("--trace", action="store_true")
    ex = sub.add_parser("extract", help="P5 L3: summarise W.Alter conversations into derived knowledge")
    ex.add_argument("--limit", type=int, default=20); ex.add_argument("--since"); ex.add_argument("--budget", default="recurring")
    ex.add_argument("--session")
    sub.add_parser("health", help="supervision: connectors freshness, failures, queues, budgets, index lag")
    sub.add_parser("privacy-rescan", help="re-run detectors and tighten privacy classes (never loosen)")
    j = sub.add_parser("jobs"); j.add_argument("action", choices=["requeue-stale"])
    g = sub.add_parser("purge", help="break-glass purge (dry-run unless --execute)")
    g.add_argument("--reason", required=True); g.add_argument("--by", required=True)
    g.add_argument("--event", action="append"); g.add_argument("--object", action="append"); g.add_argument("--pattern")
    g.add_argument("--hindsight", action="store_true"); g.add_argument("--execute", action="store_true")
    g.add_argument("--no-backup-rewrite", action="store_true")
    lg = sub.add_parser("logs", help="walter-logs: what the agents did (messages, reasoning, tool calls/results), all runtimes")
    lg.add_argument("action", choices=["search", "timeline", "get", "sessions", "stats"])
    lg.add_argument("query", nargs="?", default="", help="search: words / exact string; timeline/get: session id")
    lg.add_argument("--runtime"); lg.add_argument("--type", action="append"); lg.add_argument("--tool")
    lg.add_argument("--session"); lg.add_argument("--since"); lg.add_argument("--until")
    lg.add_argument("--seq", type=int, help="timeline: anchor event; get: the event")
    lg.add_argument("--before", type=int, default=5); lg.add_argument("--after", type=int, default=15)
    lg.add_argument("--max-chars", type=int, default=600); lg.add_argument("--limit", type=int, default=20)
    lg.add_argument("--cloud-safe", action="store_true", help="hide local_only, pseudonymise redacted_cloud")
    lg.add_argument("--json", action="store_true")
    vw = sub.add_parser("views", help="Memory Views (lot 3): attach exchanges to subjects, read a view at a depth")
    vw.add_argument("action", choices=["run", "read", "board", "stats"])
    vw.add_argument("key", nargs="?", default="", help="read: a view key (subject:…)")
    vw.add_argument("--since", help="run: ISO time to start from (else the cursor)"); vw.add_argument("--until")
    vw.add_argument("--limit", type=int, default=500); vw.add_argument("--dry", action="store_true")
    vw.add_argument("--depth", default="overview"); vw.add_argument("--domain"); vw.add_argument("--horizon")
    vw.add_argument("--max-tokens", type=int, default=800); vw.add_argument("--json", action="store_true")
    ep = sub.add_parser("episodes", help="Episodes of runs (P4): build <run_id>, pending (catch-up), show <run_id>")
    ep.add_argument("action", choices=["build", "pending", "show"]); ep.add_argument("run_id", nargs="?", default="")
    ep.add_argument("--no-summary", action="store_true")
    ob = sub.add_parser("observations", help="Sourced observations (P3): add (JSON on stdin), of a run, recent by words")
    ob.add_argument("action", choices=["add", "run", "recent"]); ob.add_argument("arg", nargs="?", default="")
    ob.add_argument("--max-age-hours", type=float, default=24)
    rn = sub.add_parser("runs", help="Walter Run Plane: runs, their tasks, model calls and links (P0, 2026-10-27)")
    rn.add_argument("action", choices=["list", "show", "sweep", "task-start", "task-end", "update", "link", "find"])
    rn.add_argument("--session", default="", help="find: the latest run of this harness session key"); rn.add_argument("run_id", nargs="?", default="")
    rn.add_argument("--limit", type=int, default=20)
    a = p.parse_args(argv)

    if a.cmd == "agent-memory":
        from . import agent_memory
        try:
            _print(agent_memory.dispatch(json.load(sys.stdin)))
        except Exception as exc:
            _print({"status": "error", "error": type(exc).__name__,
                    "text": "Agent memory operation failed; no unsafe fallback was used."})
            raise SystemExit(1)
    elif a.cmd == "stats":
        cmd_stats(a)
    elif a.cmd == "events":
        _print(events.get_events(source=a.source, event_types=a.type, thread_id=a.thread, since=a.since, text=a.text,
                                 limit=a.limit, max_privacy="cloud_allowed" if a.cloud_safe else "local_only"))
    elif a.cmd == "types":
        _print(types.list_types() if a.action == "list" else {"synced": types.sync_seed()})
    elif a.cmd == "objects":
        if a.action == "search":
            _print(objects.search(a.ref or "", kind=a.kind, source=a.source if a.source != "vault" else None,
                                  limit=a.limit, max_privacy="cloud_allowed" if a.cloud_safe else "local_only"))
        elif a.action == "get":
            print(objects.get_object(a.ref, a.dest, dest_dir=a.dest_dir,
                                     max_privacy="cloud_allowed" if a.cloud_safe else "local_only"))
        elif a.action == "stats":
            _print(objects.stats())
        else:
            from datetime import datetime
            row = objects.put_object(a.ref, a.source, links=[tuple(x.split(":", 1)) for x in a.link],
                                     captured_at=datetime.fromisoformat(a.captured) if a.captured else None,
                                     privacy_class=a.privacy)
            _print({k: row[k] for k in ("id", "created", "kind", "storage_zone", "privacy_class", "storage_key")})
    elif a.cmd == "note":
        import hashlib
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        res = events.record_event(event_type="note.recorded", source=a.source, source_account="walter-core",
                                  source_id=hashlib.sha256(f"{a.content}|{now.isoformat()}".encode()).hexdigest()[:32],
                                  occurred_at=now, content=a.content, payload={"context": a.context, "tags": a.tag},
                                  actor={"account": "walter-core", "external_id": a.source, "display_name": a.source})
        _print({"recorded": res["inserted"], "event_ids": res["event_ids"]})
    elif a.cmd == "index" and a.hide_noise:
        from . import search
        _print(search.hide_noise())
    elif a.cmd == "index":
        from . import search
        total = {}
        for _ in range(a.loops):
            out = search.index_pending()
            for k, v in out.items():
                total[k] = total.get(k, 0) + v
            if not any(out.values()):
                break
        _print(total)
    elif a.cmd == "search":
        from . import search
        res = search.search(a.query, limit=a.limit, sources=a.source, labels=a.label, since=a.since, until=a.until,
                            include_derived=not a.no_derived, rerank=a.rerank,
                            max_privacy="cloud_allowed" if a.cloud_safe else "local_only")
        _print([{k: (r[k][:300] if k == "text" else r[k]) for k in ("occurred_at", "source", "label", "actor", "text", "kind",
                                                                     "ref_id", "latency_ms")} for r in res])
    elif a.cmd == "social":
        from . import social
        if a.action == "refresh":
            _print({"identities": social.resolve_identities(), "groups": social.sync_groups(),
                    "baselines": social.compute_baselines(), "new_deviations": social.detect_deviations()})
        elif a.action == "person":
            found = social.find_entities(a.query or "")
            _print(social.person_card(found[0]["entity_id"], "cloud_allowed" if a.cloud_safe else "local_only")
                   if found else {"error": f"no person matching {a.query!r}"})
            if len(found) > 1:
                _print({"other_matches": [{k: f[k] for k in ("canonical_name", "messages", "entity_id")} for f in found[1:]]})
        else:
            with connection() as conn:
                _print(conn.execute("""select e.canonical_name, d.metric, d.observation, d.detected_on from kardex.communication_deviations d
                                       join core.entities e using (entity_id) where d.acknowledged_at is null
                                       order by d.detected_on desc limit 30""").fetchall())
    elif a.cmd == "context":
        from . import context
        res = context.get_context(a.query, include_profile=not a.no_profile)
        print(res["text"])
        if a.trace:
            _print(res["trace"])
    elif a.cmd == "extract":
        from . import extract
        _print(extract.summarize_session(a.session, a.budget) if a.session else extract.run(a.limit, a.since, a.budget))
    elif a.cmd == "health":
        from . import health
        problems, metrics = health.check()
        _print({"status": "ok" if not problems else "problems", "problems": problems, "metrics": metrics})
        if problems:
            sys.exit(1)
    elif a.cmd == "privacy-rescan":
        from . import privacy
        _print(privacy.rescan())
    elif a.cmd == "jobs":
        _print({"requeued": ingestion.requeue_stale()})
    elif a.cmd == "logs":
        from . import logs
        mp = "cloud_allowed" if a.cloud_safe else "local_only"
        with connection() as conn:
            if a.action == "search":
                res = logs.search(conn, a.query, runtime=a.runtime, types=a.type, tool=a.tool, session=a.session,
                                  since=a.since, until=a.until, limit=a.limit, max_privacy=mp)
            elif a.action == "timeline":
                res = logs.timeline(conn, a.query or a.session, around=a.seq, before=a.before, after=a.after,
                                    types=a.type, max_chars=a.max_chars, max_privacy=mp)
            elif a.action == "get":
                res = logs.get(conn, a.query or a.session, a.seq, max_privacy=mp)
            elif a.action == "sessions":
                res = logs.sessions(conn, runtime=a.runtime, text=a.query or None, since=a.since, limit=a.limit, max_privacy=mp)
            else:
                res = logs.stats(conn)
        print(json.dumps(res, default=str, ensure_ascii=False, indent=1) if a.json else logs.render(a.action, res))
    elif a.cmd == "episodes":
        from . import episodes
        if a.action == "build":
            res = episodes.build(a.run_id, summarise=not a.no_summary)
        elif a.action == "pending":
            res = episodes.pending()
        else:
            res = episodes.latest(a.run_id) or {"error": "no episode"}
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    elif a.cmd == "observations":
        from . import observations
        if a.action == "add":            # {"run_id", "task_id", "geo", "items": [Observation v1…]}
            spec = json.load(sys.stdin)
            res = observations.record(spec.get("items") or [], run_id=spec.get("run_id"), task_id=spec.get("task_id"),
                                      geo=spec.get("geo"))
        elif a.action == "run":
            res = observations.of_run(a.arg)
        else:
            res = observations.recent(a.arg, max_age_hours=a.max_age_hours)
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    elif a.cmd == "runs":
        from . import runs
        if a.action == "list":
            res = runs.recent(a.limit)
        elif a.action == "show":
            res = runs.show(a.run_id) or {"error": "unknown run"}
        elif a.action == "update":          # what is learned after the start (walter-context preflight): JSON on stdin
            spec = json.load(sys.stdin)
            res = {"ok": True, **runs.update(spec["run_id"], thread_id=spec.get("thread_id"), level=spec.get("level"),
                                             act=spec.get("act"))}
        elif a.action == "find":            # the latest run of a harness session (a runner that only knows the session)
            from .db import connect
            with connect() as conn:
                row = conn.execute("""select run_id from runs.runs where origin->>'session_id' = %s
                                      order by started_at desc limit 1""", (a.session,)).fetchone()
            res = {"run_id": str(row["run_id"]) if row else None}
        elif a.action == "link":            # {"run_id", "kind", "refs": [...]}: what the run used or produced
            spec = json.load(sys.stdin)
            for ref in spec.get("refs") or []:
                runs.link(spec["run_id"], spec["kind"], str(ref))
            res = {"linked": len(spec.get("refs") or [])}
        elif a.action == "task-start":      # a sub-agent runner (walter-router run): JSON on stdin
            spec = json.load(sys.stdin)
            res = {"task_id": runs.task_start(spec["run_id"], kind=spec.get("kind", "walter_run"), goal=spec.get("goal"),
                                              spec=spec.get("spec"), session_id=spec.get("session_id"),
                                              task_id=spec.get("task_id"))}
        elif a.action == "task-end":        # its trace (walter_logs session), routing and outcome
            spec = json.load(sys.stdin)
            n = runs.trace(spec["session_id"], spec.get("events") or [], runtime=spec.get("runtime", "walter-router"),
                           native_id=spec.get("task_id"), model=spec.get("model"), title=(spec.get("goal") or "")[:80],
                           parent_session_id=spec.get("parent_session_id"),
                           meta={"run_id": spec.get("run_id"), "task_id": spec.get("task_id")})
            if spec.get("routing"):
                runs.routing(spec["run_id"], spec["routing"], task_id=spec["task_id"])
            runs.task_end(spec["task_id"], status=spec.get("status", "ended"), result=spec.get("result"))
            res = {"events": n}
        else:
            res = {"abandoned": runs.sweep()}
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    elif a.cmd == "views":
        from . import views
        from datetime import datetime as _dt
        if a.action == "run":
            res = views.run(since=_dt.fromisoformat(a.since) if a.since else None,
                            until=_dt.fromisoformat(a.until) if a.until else None, limit=a.limit, dry=a.dry)
        elif a.action == "read":
            res = views.read({"depth": a.depth, "key": a.key or None, "domain": a.domain, "horizon": a.horizon,
                              "max_tokens": a.max_tokens})
        elif a.action == "board":
            res = views.read({"depth": "index", "domain": a.domain or "projects", "horizon": a.horizon,
                              "max_tokens": a.max_tokens})
        else:
            with connection() as conn:
                res = {r["k"]: r["n"] for r in conn.execute(
                    """select 'views' k, count(*) n from views.view union all select 'members', count(*) from views.member
                       union all select 'versions', count(*) from views.version""").fetchall()}
        if a.json or a.action in ("run", "stats") or "error" in res:
            print(json.dumps(res, default=str, ensure_ascii=False, indent=1))
        else:
            print(res.get("content") or json.dumps(res, default=str, ensure_ascii=False, indent=1))
    elif a.cmd == "purge":
        _print(purge.purge(reason=a.reason, requested_by=a.by, event_ids=a.event, object_refs=a.object,
                           pattern=a.pattern, include_hindsight=a.hindsight, execute=a.execute,
                           rewrite_backups=not a.no_backup_rewrite))


if __name__ == "__main__":
    sys.exit(main())
