"""Walter Memory pipeline service (Memory V1, 2026-11-02): the consumers of new canonical events.

core.events ──trigger, same transaction──▶ bus.events (memory.event) ──▶ consumers (gap-free cursor, retries):
  memory.extract   marks runtime threads dirty (extract2.on_bus_events); every minute the worker extracts the
                   segments that are due (extract2.tick); every hour a reconciliation sweep re-finds anything
                   uncovered (extract2.reconcile); once a day old bus rows are pruned.
The search index keeps its 2-minute timer for now (its cursor re-reads a 3-day overlap, so late commits are safe).
A failure in a consumer never touches the canonical event: it is retried, then kept as a dead letter.
Run: `walter-memory pipeline` (systemd: walter-memory-pipeline.service).
"""
from __future__ import annotations

import logging
import time

from . import bus, extract2

log = logging.getLogger("walter.pipeline")
CONSUMER = "memory.extract"
TYPES = ["memory.event"]


def shadow_working(limit: int = 20) -> int:
    """P1.1 shadow: for each runtime thread with a message newer than its last record, the working state and the
    adaptive decision, recorded in extraction.working_shadow (nothing injected, extraction unchanged)."""
    import json
    from datetime import datetime, timezone
    from . import working
    from .db import connection
    if extract2.policy() == "off":
        return 0
    with connection() as conn:
        start = extract2.v1_start(conn)
        if start is None:
            return 0
        rows = conn.execute("""
            select e.source, e.thread_id, max(e.occurred_at) as last_at
            from core.events e
            where e.source = any(%s) and e.event_type = any(%s) and e.ingested_at >= greatest(%s, now() - interval '2 days')
              and e.thread_id is not null
            group by 1, 2
            having max(e.ingested_at) > coalesce((select max(w.at) from extraction.working_shadow w
                                                  where w.source = e.source and w.thread_id = e.thread_id), '-infinity')
            order by 3 desc limit %s""", (list(extract2.RUNTIMES), list(extract2.MESSAGE_TYPES), start, limit)).fetchall()
    n = 0
    for r in rows:
        st = working.state(r["source"], r["thread_id"], audience="owner_local")
        with connection() as conn:
            msgs = extract2.pending_events(conn, r["source"], r["thread_id"],
                                           extract2._thread_start(conn, r["source"], r["thread_id"]))
        usable = [m for m in msgs if m["privacy_class"] == "cloud_allowed" and not extract2._noise(m)]
        now = datetime.now(timezone.utc)
        segs_a, _, reason = extract2.adaptive_due(usable, now)
        segs_l, _ = extract2.due_segments(usable, now)
        with connection() as conn:
            conn.execute("""insert into extraction.working_shadow (source, thread_id, last_event_at, pending, interpreted,
                                plan_items, tokens, build_ms, would_call, reason, live_due, privacy_class, state)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                         (r["source"], r["thread_id"], r["last_at"], len(st["pending"]),
                          sum(len(v) for v in st["interpreted"].values()), len(st["plan"] or []), st["tokens"],
                          st["build_ms"], bool(segs_a), reason, bool(segs_l), st["privacy_class"],
                          json.dumps(working.session_state(st), ensure_ascii=False, default=str)))
            conn.execute("delete from extraction.working_shadow where at < now() - interval '30 days'")
        n += 1
    return n


def run(tick_every: float = 60.0, reconcile_every: float = 3600.0, prune_every: float = 86400.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    last = {"reconcile": 0.0, "prune": time.monotonic()}

    def idle():
        try:
            now = time.monotonic()
            if now - last["reconcile"] >= reconcile_every:
                log.info("reconcile %s", extract2.reconcile())
                last["reconcile"] = now
            r = extract2.tick()
            if r["segments"] or r["errors"] or r.get("stopped"):
                log.info("tick %s", r)
            try:
                from . import consolidate
                if now - last.get("expire", 0.0) >= 3600:
                    r_exp = consolidate.expire()
                    last["expire"] = now
                    if r_exp["expired_task_rules"]:
                        log.info("expire %s", r_exp)
                r_views = consolidate.tick()
                if r_views.get("built"):
                    log.info("views (g1, shadow) %s", r_views)
            except Exception:
                log.exception("consolidated views failed (extraction unaffected)")
            try:   # P1.4-P1.6: flows, episodes and periods (deterministic; plans = capped model calls)
                from . import organic
                ep = organic.settings().get("episodes", {})
                if ep.get("mode", "active") != "off" and now - last.get("flows", 0.0) >= float(ep.get("every_s", 600)):
                    from . import episodic, flows, periods
                    r_f = flows.tick()
                    r_p = episodic.plans() if now - last.get("plans", 0.0) >= float(ep.get("plans_every_s", 1800)) else None
                    if r_p is not None:
                        last["plans"] = now
                    r_e = episodic.build()
                    r_t = periods.tick()
                    last["flows"] = now
                    log.info("flows %s plans %s episodes %s periods %s", {k: v for k, v in r_f.items()}, r_p, r_e, r_t)
                elif ep.get("mode", "active") != "off":
                    from . import periods
                    with __import__("walter_memory.db", fromlist=["connection"]).connection() as conn:
                        stale = periods.stale_keys(conn)
                    if stale:     # a correction: rebuild only the touched periods, without waiting for the cycle
                        log.info("periods (stale) %s", periods.tick(days=0))
            except Exception:
                log.exception("flows / episodes / periods failed (extraction unaffected)")
            try:   # Kardex enrichment from the owner's conversations (pseudonymised, capped), once a day
                from . import organic
                kx = organic.settings().get("kardex", {})
                if kx.get("mode", "daily") == "daily" and now - last.get("kardex", 0.0) >= 86400:
                    last["kardex"] = now
                    if last.get("kardex_started"):        # not at the service's start: a restart must not re-run it
                        from . import kardex_enrich
                        r_k = kardex_enrich.run()
                        log.info("kardex enrich %s", {k: v for k, v in r_k.items() if k != "results"})
                    last["kardex_started"] = True
            except Exception:
                log.exception("kardex enrichment failed (extraction unaffected)")
            try:
                shadow = shadow_working()
                if shadow:
                    log.info("working-memory shadow: %s threads recorded", shadow)
            except Exception:
                log.exception("working-memory shadow failed (extraction unaffected)")
            if now - last["prune"] >= prune_every:
                log.info("bus prune: %s rows", bus.prune())
                last["prune"] = now
        except Exception:
            log.exception("pipeline idle step failed (retried next minute)")

    bus.Consumer(CONSUMER, TYPES, batch=500, settle=2.0).run(extract2.on_bus_events, idle=idle,
                                                            idle_every=tick_every, batch=True)


def health() -> dict:
    lag = bus.lag(CONSUMER, TYPES)
    st = extract2.stats(24)
    return {"bus": lag, "extraction": st}
