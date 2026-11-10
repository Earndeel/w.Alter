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


def bus_lag(assimilation) -> dict:
    from . import bus
    return bus.lag(assimilation.CONSUMER, assimilation.TYPES)


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
    e.add_argument("--until"); e.add_argument("--id", dest="event_id"); e.add_argument("--order", choices=["asc", "desc"], default="desc")
    e.add_argument("--compact", type=int, default=0, metavar="CHARS", help="agent form: content window of CHARS, no payload")
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
    sq.add_argument("--history", action="store_true", help="also pre-V1 interpretations (archived memory generations)")
    so = sub.add_parser("social", help="P4: resolve identities, groups, baselines, deviations; person cards")
    so.add_argument("action", choices=["refresh", "person", "deviations"]); so.add_argument("query", nargs="?")
    so.add_argument("--cloud-safe", action="store_true")
    cx = sub.add_parser("context", help="P6: assemble the memory context for a query")
    cx.add_argument("query"); cx.add_argument("--no-profile", action="store_true"); cx.add_argument("--trace", action="store_true")
    cx.add_argument("--history", action="store_true", help="also pre-V1 interpretations, marked « pré-V1 »")
    ex = sub.add_parser("extract", help="P5 L3: summarise W.Alter conversations into derived knowledge")
    ex.add_argument("--limit", type=int, default=20); ex.add_argument("--since"); ex.add_argument("--budget", default="recurring")
    ex.add_argument("--session")
    x2 = sub.add_parser("extract2", help="V1 knowledge extraction, every runtime, per segment (pipeline service does it live)")
    x2.add_argument("action", choices=["tick", "thread", "reconcile", "enqueue", "replay", "stats", "start"])
    x2.add_argument("--source"); x2.add_argument("--thread"); x2.add_argument("--since")
    x2.add_argument("--status", default="failed"); x2.add_argument("--hours", type=int, default=24)
    x2.add_argument("--limit", type=int, default=8); x2.add_argument("--budget", default="recurring")
    x2.add_argument("--force", action="store_true", help="thread: also process the tail still waiting")
    pl = sub.add_parser("pipeline", help="V1 event pipeline: run the consumers (service) or show their health")
    pl.add_argument("action", nargs="?", default="run", choices=["run", "health"])
    asm = sub.add_parser("assimilation", help="event-driven P1.4-P1.6 (memory.organic): status, step (drain + work now), "
                                              "reconcile, seed (record decisions taken before the ledger)")
    asm.add_argument("action", choices=["status", "step", "reconcile", "seed"])
    asm.add_argument("--hours", type=int, default=24)
    cs = sub.add_parser("consolidate", help="P1.2 views rebuilt from current V1 knowledge (shadow): build, tick, expire, reconsolidate, show")
    cs.add_argument("action", choices=["build", "tick", "expire", "reconsolidate", "show"]); cs.add_argument("--subject")
    cs.add_argument("--depth", default="overview"); cs.add_argument("--variant", default="cloud"); cs.add_argument("--force", action="store_true")
    gn = sub.add_parser("generations", help="memory generations g0 (pre-V1) / g1 (V1): status, preview, switch, rollback")
    gn.add_argument("action", choices=["status", "preview", "switch", "rollback"]); gn.add_argument("--query", action="append")
    gn.add_argument("--to", default="g1"); gn.add_argument("--confirm", action="store_true"); gn.add_argument("--note", default="")
    bu = sub.add_parser("bus", help="Walter bus: lag, dead letters, replay, prune")
    bu.add_argument("action", choices=["lag", "dead", "replay", "prune"]); bu.add_argument("--consumer")
    bu.add_argument("--types", default="memory.event"); bu.add_argument("--event", type=int)
    bu.add_argument("--status"); bu.add_argument("--days", type=int, default=30)
    sub.add_parser("health", help="supervision: connectors freshness, failures, queues, budgets, index lag")
    sub.add_parser("privacy-rescan", help="re-run detectors and tighten privacy classes (never loosen)")
    j = sub.add_parser("jobs"); j.add_argument("action", choices=["requeue-stale"])
    g = sub.add_parser("purge", help="break-glass purge (dry-run unless --execute); reapply/verify after a restore; "
                                     "exposure = backups that may still hold purged data")
    g.add_argument("action", nargs="?", default="run", choices=["run", "reapply", "verify", "exposure"])
    g.add_argument("--reason"); g.add_argument("--by")
    g.add_argument("--event", action="append"); g.add_argument("--object", action="append"); g.add_argument("--pattern")
    g.add_argument("--execute", action="store_true")
    g.add_argument("--rotate-local-dumps", action="store_true",
                   help="after the purge: fresh dump, then shred the older rolling local dumps (never restic/keep)")
    ob = sub.add_parser("observability", help="observability vs memory: proof against walter_logs, retire the copies")
    ob.add_argument("action", choices=["proof", "retire"]); ob.add_argument("--execute", action="store_true")
    ob.add_argument("--by"); ob.add_argument("--reason"); ob.add_argument("--expect-sha")
    ob.add_argument("--out", help="also write the JSON report here")
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
    vw.add_argument("action", choices=["run", "read", "board", "stats", "find"])
    vw.add_argument("key", nargs="?", default="", help="read: a view key (subject:…)")
    vw.add_argument("--since", help="run: ISO time to start from (else the cursor)"); vw.add_argument("--until")
    vw.add_argument("--limit", type=int, default=500); vw.add_argument("--dry", action="store_true")
    vw.add_argument("--depth", default="overview"); vw.add_argument("--domain"); vw.add_argument("--horizon")
    vw.add_argument("--max-tokens", type=int, default=800); vw.add_argument("--json", action="store_true")
    vw.add_argument("--query", default="", help="find: the V1 views closest to these words (subjects, episodes, periods)")
    vw.add_argument("--local", action="store_true", help="owner reading on the VM: local_only views too")
    ds = sub.add_parser("disclosure", help="P1.7: may this outgoing message leave? allow | ask | block, with reasons")
    ds.add_argument("action", choices=["check"]); ds.add_argument("--to", default=None); ds.add_argument("--text", default=None)
    ds.add_argument("--channel", default="cli"); ds.add_argument("--no-model", action="store_true")
    ep2 = sub.add_parser("organic", help="P1.3-P1.6: entities, flows, episodes, periods (seed, link, flows, plans, episodes, periods, period)")
    ep2.add_argument("action", choices=["seed", "link", "flows", "plans", "episodes", "periods", "period", "kardex"])
    ep2.add_argument("--days", type=int, default=7); ep2.add_argument("--kind", default="day", choices=["day", "week", "month"])
    ep2.add_argument("--date", default=None); ep2.add_argument("--limit", type=int, default=None)
    mg = sub.add_parser("migrate", help="apply this module's migrations in order and record them (status, baseline)")
    mg.add_argument("--status", action="store_true"); mg.add_argument("--dry", action="store_true")
    mg.add_argument("--baseline-through", help="record files up to this name as already applied, without running them")
    mg.add_argument("--accept-change", metavar="FILE", help="record the new content of a baseline file (never run here)")
    dc = sub.add_parser("documents", help="the instance's curated records as knowledge (doc_section): sync, list")
    dc.add_argument("action", choices=["sync", "list", "register"]); dc.add_argument("--dry", action="store_true")
    ep = sub.add_parser("episodes", help="Episodes of runs (P4): build <run_id>, pending (catch-up), show <run_id>")
    ep.add_argument("action", choices=["build", "pending", "show"]); ep.add_argument("run_id", nargs="?", default="")
    ep.add_argument("--no-summary", action="store_true")
    ob = sub.add_parser("observations", help="Sourced observations (P3): add (JSON on stdin), of a run, recent by words")
    ob.add_argument("action", choices=["add", "run", "recent"]); ob.add_argument("arg", nargs="?", default="")
    ob.add_argument("--max-age-hours", type=float, default=24)
    rn = sub.add_parser("runs", help="Walter Run Plane: runs, their tasks, model calls and links (P0, 2026-10-27)")
    rn.add_argument("action", choices=["list", "show", "sweep", "task-start", "task-end", "update", "link", "find", "routing", "end"])
    rn.add_argument("--session", default="", help="find: the latest run of this harness session key"); rn.add_argument("run_id", nargs="?", default="")
    rn.add_argument("--open-only", action="store_true", help="find: unique open session run or exact run_id; metadata only")
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
        rows = events.get_events(source=a.source, event_types=a.type, thread_id=a.thread, since=a.since, until=a.until,
                                 text=a.text, limit=a.limit, order=a.order, event_id=a.event_id,
                                 max_privacy="cloud_allowed" if a.cloud_safe else "local_only")
        _print(events.compact(rows, a.text, a.compact) if a.compact else rows)
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
        from . import documents, search
        total = {}
        try:
            total.update({f"documents_{k}": v for k, v in documents.sync_if_changed().items() if k in ("new", "changed", "removed")})
        except Exception as exc:  # noqa: BLE001 — documents never block the event index
            print(f"documents: {type(exc).__name__}: {exc}", file=sys.stderr)
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
                            include_derived=not a.no_derived, rerank=a.rerank, history=a.history,
                            max_privacy="cloud_allowed" if a.cloud_safe else "local_only")
        _print([{k: (r[k][:300] if k == "text" else r.get(k)) for k in ("occurred_at", "source", "label", "actor", "text", "kind",
                                                                         "ref_id", "generation", "latency_ms")} for r in res])
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
        res = context.get_context(a.query, include_profile=not a.no_profile, history=a.history)
        print(res["text"])
        if a.trace:
            _print(res["trace"])
    elif a.cmd == "extract":
        from . import extract
        _print(extract.summarize_session(a.session, a.budget) if a.session else extract.run(a.limit, a.since, a.budget))
    elif a.cmd == "extract2":
        from . import extract2
        if a.action == "tick":
            _print(extract2.tick(a.limit, budget=a.budget))
        elif a.action == "thread":
            if not (a.source and a.thread):
                p.error("extract2 thread needs --source and --thread")
            _print(extract2.process_thread(a.source, a.thread, budget=a.budget, force=a.force))
        elif a.action == "reconcile":
            _print(extract2.reconcile())
        elif a.action == "enqueue":
            if not (a.since or a.thread):
                p.error("extract2 enqueue needs --since or --thread (no automatic pre-V1 backfill)")
            _print({"threads_marked": extract2.enqueue(since=a.since, thread=a.thread, source=a.source)})
        elif a.action == "replay":
            _print({"segments_replayed": extract2.replay(status=a.status, thread=a.thread)})
        elif a.action == "start":
            from datetime import datetime as _dt
            _print({"v1_start": extract2.set_v1_start(_dt.fromisoformat(a.since) if a.since else None)})
        else:
            _print(extract2.stats(a.hours))
    elif a.cmd == "pipeline":
        from . import pipeline
        pipeline.run() if a.action == "run" else _print(pipeline.health())
    elif a.cmd == "assimilation":
        from . import assimilation, episodic, processing
        if a.action == "status":
            _print({"engine": assimilation.engine(), "bus": bus_lag(assimilation), "backlog": processing.backlog(),
                    "summary": processing.summary(a.hours)})
        elif a.action == "step":
            _print(assimilation.step())
        elif a.action == "reconcile":
            _print(assimilation.reconcile())
        else:
            _print(episodic.seed_ledger())
    elif a.cmd == "consolidate":
        from . import consolidate, views
        if a.action in ("build", "reconsolidate", "show") and not a.subject:
            p.error(f"consolidate {a.action} needs --subject")
        if a.action == "build":
            _print(consolidate.build_subject(a.subject, force=a.force))
        elif a.action == "tick":
            _print(consolidate.tick())
        elif a.action == "expire":
            _print(consolidate.expire())
        elif a.action == "reconsolidate":
            _print(consolidate.reconsolidate(a.subject))
        else:
            r = views.read({"depth": a.depth, "key": consolidate.key_for(a.subject, a.variant), "shadow": True,
                            "privacy": "local_only" if a.variant == "local" else "cloud_allowed", "max_tokens": 6000})
            print(r.get("content") or r)
    elif a.cmd == "generations":
        from . import generations
        if a.action == "status":
            _print(generations.status())
        elif a.action == "preview":
            if not a.query:
                p.error("generations preview needs --query (repeatable)")
            _print([generations.preview(q) for q in a.query])
        elif a.action == "switch":
            _print(generations.switch(a.to, confirm=a.confirm, note=a.note))
        else:
            _print(generations.rollback(confirm=a.confirm))
    elif a.cmd == "bus":
        from . import bus
        if a.action == "lag":
            _print(bus.lag(a.consumer or "memory.extract", a.types.split(",")))
        elif a.action == "dead":
            _print(bus.dead(a.consumer, a.status))
        elif a.action == "replay":
            if not a.consumer:
                p.error("bus replay needs --consumer")
            _print({"replayed": bus.replay(a.consumer, a.event, a.status or "dead")})
        else:
            _print({"pruned": bus.prune(a.days)})
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
    elif a.cmd == "migrate":
        from . import migrate
        res = (migrate.status() if a.status else migrate.accept_change(a.accept_change) if a.accept_change
               else migrate.migrate(baseline_through=a.baseline_through, dry_run=a.dry))
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
    elif a.cmd == "documents":
        from . import documents
        res = (documents.sync(dry_run=a.dry) if a.action == "sync" else documents.register() or {"registered": True}
               if a.action == "register" else documents.listing())
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
                                             act=spec.get("act"), requested=spec.get("requested"))}
        elif a.action == "find":            # the latest run of a harness session (a runner that only knows the session)
            from .db import connect
            fields = ("run_id, status, privacy_class, origin->>'channel' as channel, routing->'requested' as requested"
                      if a.open_only else "run_id")
            opened = "and status = 'open'" if a.open_only else ""
            by_id = a.open_only and bool(a.run_id)
            identity = "run_id" if by_id else "origin->>'session_id'"
            reference = a.run_id if by_id else a.session
            limit = 2 if a.open_only and not by_id else 1
            with connect() as conn:
                rows = conn.execute(f"""select {fields} from runs.runs where {identity} = %s {opened}
                                        order by started_at desc limit {limit}""", (reference,)).fetchall()
            ambiguous = len(rows) > 1
            row = rows[0] if rows and not ambiguous else None
            res = {"run_id": str(row["run_id"]) if row else None}
            if a.open_only:
                res.update({key: row[key] if row else None for key in ("status", "privacy_class", "channel", "requested")})
                if ambiguous:
                    res["error"] = "ambiguous_open_runs"
        elif a.action == "routing":         # observed route only; caller content never enters the decision
            if not a.run_id:
                p.error("runs routing requires an explicit run_id")
            spec = json.load(sys.stdin)
            if not isinstance(spec, dict):
                p.error("runs routing expects a JSON object on stdin")
            decision = {key: spec[key] for key in ("applied", "via", "model_id", "model", "provider", "observed_model")
                        if key in spec}
            runs.routing(a.run_id, decision)
            res = {"ok": True}
        elif a.action == "end":             # explicit completion, including harness errors without a Stop hook
            if not a.run_id:
                p.error("runs end requires an explicit run_id")
            spec = json.load(sys.stdin)
            if not isinstance(spec, dict) or spec.get("status") not in ("ended", "failed", "cancelled"):
                p.error("runs end expects an explicit status: ended, failed or cancelled")
            runs.end(a.run_id, status=spec["status"])
            res = {"ok": True}
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
            # no events = the executor keeps its own trace (Walter Engine: its session is in walter_logs already)
            n = runs.trace(spec["session_id"], spec["events"], runtime=spec.get("runtime", "walter-router"),
                           native_id=spec.get("task_id"), model=spec.get("model"), title=(spec.get("goal") or "")[:80],
                           parent_session_id=spec.get("parent_session_id"),
                           meta={"run_id": spec.get("run_id"), "task_id": spec.get("task_id")}) if spec.get("events") else 0
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
                              "max_tokens": a.max_tokens, "privacy": "local_only" if a.local else "cloud_allowed"})
        elif a.action == "board":
            res = views.read({"depth": "index", "domain": a.domain or "projects", "horizon": a.horizon,
                              "max_tokens": a.max_tokens})
        elif a.action == "find":
            from . import consolidate
            lines = consolidate.related_views(a.query or a.key, max_privacy="local_only" if a.local else "cloud_allowed",
                                              limit=10, min_sim=0.2)
            res = {"content": "\n".join(lines) or "(aucune vue V1 proche)"}
        else:
            with connection() as conn:
                res = {r["k"]: r["n"] for r in conn.execute(
                    """select 'views' k, count(*) n from views.view union all select 'members', count(*) from views.member
                       union all select 'versions', count(*) from views.version""").fetchall()}
        if a.json or a.action in ("run", "stats") or "error" in res:
            print(json.dumps(res, default=str, ensure_ascii=False, indent=1))
        else:
            print(res.get("content") or json.dumps(res, default=str, ensure_ascii=False, indent=1))
    elif a.cmd == "disclosure":
        from . import disclosure
        text = a.text if a.text is not None else sys.stdin.read()
        r = disclosure.check(text, to=a.to, channel=a.channel, model=not a.no_model)
        _print({**r, "explanation": disclosure.explain(r)})
    elif a.cmd == "organic":
        from datetime import date as _d, datetime as _dt, timedelta as _td, timezone as _tz
        since = _dt.now(_tz.utc) - _td(days=a.days)
        if a.action == "seed":
            from . import entities
            _print(entities.seed())
        elif a.action == "link":
            from . import entities
            _print(entities.link_items())
        elif a.action == "flows":
            from . import flows
            _print(flows.tick(since))
        elif a.action == "plans":
            from . import episodic
            _print(episodic.plans(since, limit=a.limit))
        elif a.action == "episodes":
            from . import episodic
            _print(episodic.build(since))
        elif a.action == "periods":
            from . import periods
            _print(periods.tick(days=a.days))
        elif a.action == "kardex":
            from . import kardex_enrich
            r = kardex_enrich.run(a.limit)
            _print({k: v for k, v in r.items() if k != "results"} | {"per_contact": [
                {k: v for k, v in x.items() if k in ("messages", "claims", "reused", "rejected", "skipped", "error")}
                for x in r["results"]]})
        else:
            from . import periods
            _print(periods.build(a.kind, _d.fromisoformat(a.date) if a.date else _dt.now(_tz.utc).date(), force=True))
    elif a.cmd == "purge":
        if a.action == "verify":
            _print(purge.verify())
        elif a.action == "exposure":
            _print(purge.exposure())
        elif not a.by or (a.action == "run" and not a.reason):
            p.error("purge run needs --reason and --by; purge reapply needs --by")
        elif a.action == "reapply":
            _print(purge.reapply(requested_by=a.by, execute=a.execute))
        else:
            _print(purge.purge(reason=a.reason, requested_by=a.by, event_ids=a.event, object_refs=a.object,
                               pattern=a.pattern, execute=a.execute, rotate_local_dumps=a.rotate_local_dumps))
    elif a.cmd == "observability":
        from . import observability
        if a.action == "retire" and (not a.by or not a.reason):
            p.error("observability retire needs --by and --reason")
        r = observability.proof() if a.action == "proof" else observability.retire(
            requested_by=a.by, reason=a.reason, execute=a.execute, expect_sha=a.expect_sha)
        if a.out:
            from pathlib import Path
            Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str) + "\n")
        _print(r)


if __name__ == "__main__":
    sys.exit(main())
