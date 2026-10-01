"""Walter Memory health (P7 supervision, §8.1): freshness per connector, failures, queues, budgets, index lag,
privacy flags. Returns problems as short strings (empty = healthy) plus a metrics dict."""
from __future__ import annotations

from .db import connection
from .llm import budget_status


def check() -> tuple[list[str], dict]:
    problems, m = [], {}
    with connection() as conn:
        for c in conn.execute("""select connector, enabled, freshness_target, last_success_at, last_error, last_error_at,
                                        now() - last_success_at as age from ingestion.connectors where enabled""").fetchall():
            m[f"age:{c['connector']}"] = str(c["age"])
            if c["freshness_target"] and c["last_success_at"] and c["age"] > 3 * c["freshness_target"]:
                problems.append(f"{c['connector']}: no successful run for {c['age']} (target {c['freshness_target']})")
            if c["last_error_at"] and (not c["last_success_at"] or c["last_error_at"] > c["last_success_at"]):
                problems.append(f"{c['connector']}: last run failed — {(c['last_error'] or '')[:120]}")
        dead = conn.execute("select queue, count(*) n from ingestion.jobs where status = 'dead' group by 1").fetchall()
        problems += [f"queue {d['queue']}: {d['n']} dead jobs" for d in dead]
        stuck = conn.execute("""select count(*) n from ingestion.jobs where status = 'running' and locked_at < now() - interval '1 hour'""").fetchone()["n"]
        if stuck:
            problems.append(f"{stuck} jobs stuck in running")
        lag = conn.execute("""select count(*) n from core.events e where e.ingested_at < now() - interval '30 minutes'
                              and e.content is not null and length(e.content) > 1
                              and e.event_type in ('message.received','message.sent','email.received','email.sent','calendar.event','note.recorded')
                              and e.ingested_at > now() - interval '2 days'
                              and not exists (select 1 from search.chunks c where c.kind = 'event' and c.ref_id = e.event_id)""").fetchone()["n"]
        m["index_lag"] = lag
        if lag > 500:
            problems.append(f"search index lagging: {lag} recent events not indexed")
        secrets = conn.execute("""select count(*) n from privacy.detections where category = 'secret' and reviewed_at is null
                                  and at > now() - interval '1 day'""").fetchone()["n"]
        m["new_secret_flags_24h"] = secrets
    for b in ("recurring", "backfill"):
        s = budget_status(b)
        m[f"budget:{b}"] = f"{float(s['spent_usd']):.2f}/{float(s['limit_usd']):.0f}"
        if float(s["spent_usd"]) >= 0.8 * float(s["limit_usd"]):
            problems.append(f"budget {b} at {float(s['spent_usd']):.2f}/{float(s['limit_usd']):.0f} USD this month")
    return problems, m
