"""Walter Memory health (P7 supervision, §8.1): freshness per connector, failures, queues, budgets, index lag,
privacy flags, model-call error rate per processor and decisions taken by fallback (SOCLE A8, 2026-11-11: 409 failed
model calls in 4 h had stayed invisible). Returns problems as short strings (empty = healthy) plus a metrics dict;
`metrics["errors"]` lists the problems of severity error (prefix `model_calls:`), the others are warnings."""
from __future__ import annotations

import re
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

from .db import connection
from .llm import ACCOUNT_FLOOR_USD, account_balance, budget_status

ERROR_PREFIXES = ("model_calls:",)
DEFAULTS = {"model_calls": {"window_min": 30, "min_calls": 5, "error_ratio": 0.5},
            "triage": {"window_h": 24, "min_errors": 5}}
_MASKS = [
    (re.compile(r"(?i)(bearer\s+)\S+"), r"\1***"),
    (re.compile(r"(?i)((?:password|passwd|secret|token|api[_-]?key|authorization|session)[\"']?\s*[:=]\s*)\S+"), r"\1***"),
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"(?:~|\.{0,2})?/[\w.@+-]+(?:/[\w.@+-]+)+"), "<path>"),
    (re.compile(r"\b[A-Za-z0-9_+/=-]{24,}\b"), "***"),
]


@lru_cache(maxsize=1)
def settings() -> dict:
    """config/health.toml, the instance override first; defaults when absent or unreadable."""
    path = None
    try:
        path = subprocess.run(["walter", "instance", "config", "memory", "health.toml"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    p = Path(path) if path else Path(__file__).resolve().parent.parent / "config" / "health.toml"
    try:
        data = tomllib.loads(p.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    return {k: {**v, **(data.get(k) or {})} for k, v in DEFAULTS.items()}


def mask_error(text: str | None, limit: int = 80) -> str:
    """Error class for a health line: no URL, no path, no token; first `limit` characters."""
    t = " ".join(str(text or "").split())
    for pat, rep in _MASKS:
        t = pat.sub(rep, t)
    return t[:limit]


def severity(problem: str) -> str:
    return "error" if problem.startswith(ERROR_PREFIXES) else "warning"


def model_call_problems(rows: list[dict], cfg: dict | None = None) -> list[str]:
    """rows: {processor, calls, failed, dominant} over the window. A processor with at least `min_calls` calls and a
    failed ratio above `error_ratio` is a problem `model_calls:<processor>:<ratio> — …` (severity error)."""
    cfg = cfg or DEFAULTS["model_calls"]
    out = []
    for r in rows:
        calls, failed = int(r.get("calls") or 0), int(r.get("failed") or 0)
        if calls < int(cfg["min_calls"]) or not calls:
            continue
        ratio = failed / calls
        if ratio > float(cfg["error_ratio"]):
            out.append(f"model_calls:{r['processor']}:{ratio:.2f} — {failed}/{calls} model calls failed in "
                       f"{cfg['window_min']} min: {mask_error(r.get('dominant'))}")
    return out


def triage_problems(errors: int, total: int, cfg: dict | None = None) -> list[str]:
    cfg = cfg or DEFAULTS["triage"]
    if errors >= int(cfg["min_errors"]):
        return [f"triage: {errors}/{total} decisions in {cfg['window_h']} h taken without the model (payload.error, rule fallback)"]
    return []


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
        # a dead job is a problem while it is recent (a week of alerts); older ones are known source-side losses
        # (asset deleted on the phone, transfer refused): kept as a metric, they never age into a permanent alarm
        dead = conn.execute("""select queue, count(*) filter (where finished_at > now() - interval '7 days') recent,
                                      count(*) n from ingestion.jobs where status = 'dead' group by 1""").fetchall()
        problems += [f"queue {d['queue']}: {d['recent']} dead jobs this week" for d in dead if d["recent"]]
        m["dead_jobs_old"] = sum(d["n"] - d["recent"] for d in dead)
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
        cfg = settings()
        # 'dropped' = a late sample of a multi-sample decision the gateway did not wait for: neither ok nor failed
        mc = conn.execute("""select processor, count(*) filter (where status <> 'dropped') calls,
                                    count(*) filter (where status not in ('ok', 'dropped')) failed,
                                    mode() within group (order by left(error, 200))
                                        filter (where status not in ('ok', 'dropped')) dominant
                             from system.model_calls where at > now() - make_interval(mins => %s)
                             group by 1""", (int(cfg["model_calls"]["window_min"]),)).fetchall()
        m["model_calls_window"] = {r["processor"]: {"calls": r["calls"], "failed": r["failed"]} for r in mc}
        problems += model_call_problems(mc, {**cfg["model_calls"]})
    try:   # triage decisions recorded with payload.error: the model failed and a rule decided instead
        with connection() as conn:
            t = conn.execute("""select count(*) filter (where nullif(payload->>'error', '') is not null) errors,
                                       count(*) total from triage.decisions
                                where decided_at > now() - make_interval(hours => %s)""",
                             (int(cfg["triage"]["window_h"]),)).fetchone()
        m["triage_errors"] = {"errors": t["errors"], "total": t["total"]}
        problems += triage_problems(t["errors"], t["total"], cfg["triage"])
    except Exception as e:  # noqa: BLE001 — schema absent on a fresh database
        m["triage_errors"] = f"unreadable: {type(e).__name__}"
    try:   # Memory V1 pipeline: bus delivery and extraction freshness (a notification is not proof of memory)
        from . import bus, extract2
        lg = bus.lag("memory.extract", ["memory.event"])
        m["bus:memory.extract"] = lg
        if lg["oldest_s"] > 900:
            problems.append(f"memory pipeline {lg['oldest_s'] // 60} min behind on the bus ({lg['pending']} events)")
        if lg["held"] > 1000:
            problems.append(f"{lg['held']} bus events held behind a long-running transaction")
        if lg["dead"]:
            problems.append(f"memory pipeline: {lg['dead']} dead letters (walter-memory bus dead / replay)")
        st = extract2.stats(24)
        m["extraction_backlog"] = st["backlog"]
        if (st["backlog"]["oldest_s"] or 0) > 6 * 3600:
            problems.append(f"extraction backlog: {st['backlog']['n']} messages, oldest waiting "
                            f"{st['backlog']['oldest_s'] // 3600} h")
        failed = next((r["segments"] for r in st["segments"] if r["status"] == "failed"), 0)
        if failed:
            problems.append(f"extraction: {failed} segments failed in 24 h (walter-memory extract2 replay)")
        # event-driven assimilation (memory.organic, 2026-11-03): delivery, overdue keys, failing processors
        from . import assimilation, processing
        if assimilation.engine() == "events":
            lo = bus.lag(assimilation.CONSUMER, assimilation.TYPES)
            m["bus:memory.organic"] = lo
            if lo["oldest_s"] > 900:
                problems.append(f"memory assimilation {lo['oldest_s'] // 60} min behind on the bus ({lo['pending']} events)")
            for b in processing.backlog():
                if (b["oldest_due_s"] or 0) > 3600:
                    problems.append(f"assimilation {b['processor']}: {b['due']} keys overdue for {b['oldest_due_s'] // 60} min")
                if b["failing"]:
                    problems.append(f"assimilation {b['processor']}: {b['failing']} keys failing (walter-memory assimilation status)")
            m["assimilation_24h"] = {r["processor"]: {k: int(v or 0) for k, v in r.items() if k != "processor"}
                                     for r in processing.summary(24)}
            for proc, st24 in m["assimilation_24h"].items():   # errors counted, not hidden behind a fallback
                if st24.get("errors"):
                    problems.append(f"assimilation {proc}: {st24['errors']} processing errors in 24 h")
    except Exception as e:
        problems.append(f"memory pipeline health unreadable: {type(e).__name__}")
    try:        # purged data must stay purged, including after a restore (purge ledger, cleanup phase 2)
        from . import purge
        v = purge.verify()
        m["purge_ledger"] = {"targets": sum(v["ledger"].values()), "present_again": v["present_again"]}
        if not v["ok"]:
            problems.append("purged data present again (restore?): walter-memory purge reapply --by … --execute")
    except Exception as e:  # noqa: BLE001
        problems.append(f"purge ledger unreadable: {type(e).__name__}")
    for b in ("recurring", "backfill"):
        s = budget_status(b)
        m[f"budget:{b}"] = f"{float(s['spent_usd']):.2f}/{float(s['limit_usd']):.0f}"
        if float(s["spent_usd"]) >= 0.8 * float(s["limit_usd"]):
            problems.append(f"budget {b} at {float(s['spent_usd']):.2f}/{float(s['limit_usd']):.0f} USD this month")
    bal = account_balance()
    if bal is not None:
        m["openrouter_balance_usd"] = round(bal, 2)
        if bal < ACCOUNT_FLOOR_USD["recurring"] * 2:
            problems.append(f"OpenRouter balance low: {bal:.2f} USD (synthesis stops below {ACCOUNT_FLOOR_USD['recurring']} USD)")
    m["errors"] = [p for p in problems if severity(p) == "error"]
    return problems, m
