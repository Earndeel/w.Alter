"""Event-driven assimilation of Memory V1 (P1.4-P1.6, 2026-11-03): each new event triggers only what it touches.

  bus (memory.event / memory.derived / memory.view) ──▶ consumer memory.organic ──route()──▶ processing.queue
                                                                                              │ work(): due keys,
  core.derived_items / views.*  ◀── flows · plans · episodes · periods ◀──────────────────────┘ in dependency order
        └── trigger: every meaningful change of a V1 item is published (memory.derived), same transaction ──▶ bus

What an event marks (one key per processor, coalesced; settle = calm before computing, a deadline for plans):
  new Raw Vault object (text = false)    media.derive        the object id, when its kind is on ([media], A5)
  any text event / V1 item / object text  search.index        'pending' (the index's own cursor), within ~10 s
  incoming message, e-mail, calendar      triage              'incoming', after 2 min of calm (≤ 10 min while busy)
  location.sample (overland)              flows.visits        'gps', the samples' time range
  chat message (beeper, gmail)            flows.conversations source␟thread, from the message's time
  calendar.event                          flows.appointments  the calendar event id (latest version wins)
  agent message (hermes, claude_code, …)  flows.work_sessions source␟thread, local days
  event.retracted                         as its target event (a correction recomputes what the target fed)
  memory.derived conversation (owner)     episodic.plans      the burst, due BURST_SETTLE after its last message
  memory.derived appointment/plan/visit   episodic.episodes   the local days of the signal (old and new position)
  memory.derived owner statement (l3)     episodic.episodes   the days whose episodes it may attest
  memory.derived any V1 item              periods.*           its day, week and month (commitments: every period
                                                              from its date to today, they are listed while open)
  memory.view episode                     periods.*           the days of the episode
Model calls happen only in plans and attestation, through processing.decide_once: unchanged inputs reuse their recorded
decision (negative ones too). Writes happen only when something differs, so an unchanged recomputation publishes
nothing and the propagation stops by itself.
Periodic work is limited to: deadlines (the queue's due times, checked every minute), the reconciliation pass
(`reconcile`, every RECONCILE_S: recompute the windows; any difference it writes is a missed event, counted) and the
sources' own polling (connectors). Engine switch: organic.toml [episodes] engine = "events" | "timer" | "off".
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone

from . import bus, processing
from .db import connection

log = logging.getLogger("walter.assimilation")
CONSUMER = "memory.organic"
TYPES = ["memory.event", "memory.derived", "memory.view", "memory.object"]
TRIAGE_IN = {("beeper", "message.received"), ("gmail", "email.received"), ("calendar", "calendar.event")}
SEP = "\x1f"
CHAT = ("beeper", "gmail")
CHAT_TYPES = ("message.sent", "message.received", "email.sent", "email.received")
RUNTIMES = ("hermes", "claude_code", "codex", "dsh")
AGENT_TYPES = ("message.sent", "message.received")
OBSERVATIONS = ("conversation", "appointment", "visit", "work_session")
SIGNALS = ("appointment", "plan", "visit")
# settle delays (s): a burst of events → one computation
SETTLE = {"flows.visits": 300, "flows.conversations": 60, "flows.appointments": 30, "flows.work_sessions": 120,
          "episodic.episodes": 30}
BURST_SETTLE = timedelta(minutes=15)      # plans are read once a burst has been calm this long (a deadline)
ORDER = ["search.index", "search.reindex", "triage", "flows.visits", "flows.conversations", "flows.appointments", "flows.work_sessions", "episodic.plans",
         "episodic.episodes", "periods.day", "periods.week", "periods.month",
         "media.derive"]   # last: model calls of a media burst never delay the index, triage or flows
RECONCILE_S = 6 * 3600
COMMITMENT_DAYS = 62


def engine() -> str:
    from . import organic
    ep = organic.settings().get("episodes", {})
    if ep.get("mode", "active") == "off":
        return "off"
    return ep.get("engine", "events")


def _ts(v) -> datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v
    try:
        t = datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _local_day(t: datetime) -> date:
    from .flows import tz
    return t.astimezone(tz()).date()


# ───────────────────────────── routing: event → dirty keys ─────────────────────────────
def _route_event(conn, p: dict, subject: str | None) -> int:
    """A canonical event (memory.event payload) → the search index, the triage of incoming events, the flow keys."""
    from .search import TEXT_EVENT_TYPES
    et, src, thread, at = p.get("event_type"), p.get("source"), p.get("thread_id"), _ts(p.get("occurred_at"))
    if et in TEXT_EVENT_TYPES or et == "event.retracted":
        processing.mark(conn, "search.index", "pending", reason="event", settle=10, max_wait=60)
    if (src, et) in TRIAGE_IN:        # one decision per thread after 2 min of calm, at least every 10 min while busy
        processing.mark(conn, "triage", "incoming", reason=src, settle=120, max_wait=600)
    if et == "event.retracted" and subject:
        t = conn.execute("""select e.event_type, e.source, e.thread_id, e.occurred_at, e.payload->>'event_id' cal
                            from core.events r join core.events e on e.event_id::text = r.payload->>'target_event_id'
                            where r.event_id::text = %s""", (subject,)).fetchone()
        if not t:
            return 0
        if t["source"] == "calendar" and t["cal"]:
            processing.mark(conn, "flows.appointments", t["cal"], reason="retracted", settle=SETTLE["flows.appointments"])
            return 1
        return _route_event(conn, {"event_type": t["event_type"], "source": t["source"], "thread_id": t["thread_id"],
                                   "occurred_at": t["occurred_at"]}, None)
    if at is None:
        return 0
    if src == "overland" and et == "location.sample":
        processing.mark(conn, "flows.visits", "gps", at_from=at, reason="gps", settle=SETTLE["flows.visits"],
                        max_wait=900)
        return 1
    if src in CHAT and et in CHAT_TYPES + ("message.edited",) and thread:
        processing.mark(conn, "flows.conversations", src + SEP + thread, at_from=at, reason="message",
                        settle=SETTLE["flows.conversations"])
        return 1
    if src == "calendar" and et == "calendar.event" and subject:
        r = conn.execute("select payload->>'event_id' cal from core.events where event_id::text = %s", (subject,)).fetchone()
        processing.mark(conn, "flows.appointments", (r and r["cal"]) or subject, reason="calendar",
                        settle=SETTLE["flows.appointments"])
        return 1
    if src in RUNTIMES and et in AGENT_TYPES and thread:
        processing.mark(conn, "flows.work_sessions", src + SEP + thread, at_from=at, reason="agent message",
                        settle=SETTLE["flows.work_sessions"])
        return 1
    return 0


def _route_derived(conn, item_id: str, p: dict) -> int:
    """A V1 knowledge item changed (memory.derived payload) → what depends on it."""
    from . import periods
    kind, by, n = p.get("kind"), p.get("derived_by"), 0
    at, old_at = _ts(p.get("at")), _ts(p.get("old_at"))
    processing.mark(conn, "search.index", "pending", reason="knowledge", settle=10, max_wait=60)
    if p.get("op") == "update":            # its chunks must follow its new text or status (index_pending adds only)
        processing.mark(conn, "search.reindex", item_id, reason=p.get("status") or "update", settle=10, max_wait=120)
    if kind == "conversation" and by == "flows.conversations" and \
            (int(p.get("owner_messages") or 0) > 0 or p.get("status") != "derived"):
        if p.get("status") != "derived":     # the burst is gone: its plans go now
            processing.mark(conn, "episodic.plans", item_id, reason="burst gone")
        else:                                # read once the burst has been calm BURST_SETTLE (a deadline)
            end = _ts(p.get("end")) or at or datetime.now(timezone.utc)
            processing.mark(conn, "episodic.plans", item_id, reason="burst", due=end + BURST_SETTLE, settle=30)
        n += 1
    if kind in SIGNALS:
        days = {_local_day(t) for t in (at, old_at, _ts(p.get("end"))) if t}
        for d in days:
            processing.mark(conn, "episodic.episodes", d.isoformat(), reason=kind, settle=SETTLE["episodic.episodes"])
        n += len(days)
    if by == "l3.extract" and p.get("epistemic") == "stated_owner" and at:
        # the episodes this statement may attest: it is read for episodes from 3 days before it to 6 h after
        for k in range(-3, 1):
            d = _local_day(at + timedelta(days=k))
            processing.mark(conn, "episodic.episodes", d.isoformat(), reason="statement", settle=SETTLE["episodic.episodes"])
        d6 = _local_day(at + timedelta(hours=6))
        processing.mark(conn, "episodic.episodes", d6.isoformat(), reason="statement", settle=SETTLE["episodic.episodes"])
        n += 1
    # periods read the owner's knowledge (l3) and the observations; episodes reach them as views (memory.view)
    if not ((by == "l3.extract" and kind in periods.TITLES) or kind in OBSERVATIONS):
        return n
    days: set[date] = set()
    for t in (at, old_at):
        if t:
            days.add(_local_day(t))
    if kind == "commitment" and at:   # listed in every period while open
        today = _local_day(datetime.now(timezone.utc))
        d = _local_day(at)
        while d <= today and len(days) < COMMITMENT_DAYS:
            days.add(d)
            d += timedelta(days=1)
    for d in days:
        periods.mark(conn, d, reason=kind or "item")
    return n + len(days)


def _route_view(conn, view_key: str, p: dict) -> int:
    from . import periods
    if p.get("kind") != "episode":
        return 0
    start, end = _ts(p.get("starts_at")), _ts(p.get("ends_at"))
    days = {_local_day(t) for t in (start, end) if t}
    for d in days:
        periods.mark(conn, d, reason="episode")
    return len(days)


def route(evs: list[dict]) -> int:
    """Bus handler (batch, idempotent): marks the keys these events touch. Cheap: no computation here. Marks are kept
    under the timer engine too (only `work` waits for "events"), so switching engines loses nothing."""
    if engine() == "off":
        return 0
    n = 0
    with connection() as conn:
        for ev in evs:
            p = ev.get("payload") or {}
            if ev["type"] == "memory.event":
                n += _route_event(conn, p, ev.get("subject"))
            elif ev["type"] == "memory.derived":
                n += _route_derived(conn, ev["subject"], p)
            elif ev["type"] == "memory.view":
                n += _route_view(conn, ev["subject"], p)
            elif ev["type"] == "memory.object" and p.get("text") is False:   # a new file → its derived text (A5)
                from . import media
                n += media.route(conn, ev["subject"], p)
            elif ev["type"] == "memory.object":     # a file's derived text (OCR, transcript…) → the search index
                processing.mark(conn, "search.index", "pending", reason="object", settle=10, max_wait=60)
                n += 1
    return n


# ───────────────────────────── work: due keys → processors ─────────────────────────────
def _run_one(processor: str, row: dict) -> dict:
    from . import episodic, flows, periods
    key, lo, hi = row["key"], row["range_from"], row["range_to"]
    if processor == "media.derive":       # A5: a Raw Vault object's derived text (raises → retried with backoff)
        from . import media
        return media.run_key(key)
    if processor == "search.index":
        from . import search
        with connection() as conn:   # the indexer's checkpoint row needs its connector (as registered in production)
            conn.execute("""insert into ingestion.connectors (connector, source, mode, description)
                            values ('search_indexer', 'walter', 'agent', 'search.chunks indexer (derived, rebuildable)')
                            on conflict do nothing""")
        r = search.index_pending()
        return {"changed": sum(v for v in r.values() if isinstance(v, int))}
    if processor == "search.reindex":
        from . import search
        r = search.reindex_derived([key])
        return {"changed": r["reindexed"] + r["removed"]}
    if processor == "triage":
        from . import ingestion, triage
        r = triage.run()
        ingestion.mark_success(triage.CONNECTOR)
        return {"changed": int(r.get("decided", 0) or 0)}
    if processor == "flows.visits":
        return flows.visits(since=(lo or datetime.now(timezone.utc)) - flows.MAX_GAP,
                            until=(hi or lo or datetime.now(timezone.utc)) + timedelta(minutes=1))
    if processor == "flows.conversations":
        src, thread = key.split(SEP, 1)
        return flows.conversations(since=lo or datetime.now(timezone.utc) - timedelta(days=2), thread=(src, thread))
    if processor == "flows.appointments":
        return flows.appointments(calendar_event=key)
    if processor == "flows.work_sessions":
        src, thread = key.split(SEP, 1)
        now = datetime.now(timezone.utc)
        return flows.work_sessions(since=lo or now, until=hi or lo or now, thread=(src, thread))
    if processor == "episodic.plans":
        return episodic.plan_burst(key)
    if processor == "episodic.episodes":
        return episodic.build_day(date.fromisoformat(key))
    if processor.startswith("periods."):
        return periods.build_key(processor.split(".", 1)[1], key)
    raise ValueError(f"unknown processor {processor}")


def _changed(processor: str, r: dict) -> int:
    if processor.startswith("periods."):
        return sum(1 for v in r.values() if isinstance(v, dict) and v.get("rebuilt"))
    return int(r.get("changed", 0) or 0) + int(r.get("retracted", 0) or 0) + int(r.get("retired", 0) or 0) + \
        int(r.get("plans", 0) or 0) * (not r.get("reused", True))


_lock = threading.Lock()


def work(now: datetime | None = None, max_seconds: float = 50.0) -> dict:
    """Process the due keys, upstream first. Bounded in time; what is left stays due. Never raises."""
    if engine() != "events":
        return {}
    if not _lock.acquire(blocking=False):
        return {}
    out: dict[str, dict] = {}
    t0 = time.monotonic()
    try:
        for proc in ORDER:
            for row in processing.due(proc, now):
                if time.monotonic() - t0 > max_seconds:
                    return out
                o = out.setdefault(proc, {"keys": 0, "changed": 0, "errors": 0})
                try:
                    r = _run_one(proc, row)
                except Exception as e:  # noqa: BLE001 — retried with backoff, never lost
                    log.exception("assimilation: %s %s failed", proc, row["key"][:60])
                    processing.failed(row, e)
                    processing.count(proc, keys=1, errors=1)
                    o["errors"] += 1
                    continue
                c = _changed(proc, r if isinstance(r, dict) else {})
                processing.done(row)
                processing.count(proc, keys=1, changed=c)
                o["keys"] += 1
                o["changed"] += c
    finally:
        _lock.release()
    return out


# ───────────────────────────── reconciliation and deadlines ─────────────────────────────
def reconcile() -> dict:
    """The safety net, not the engine: recompute the recent windows. Writes happen only where the event-driven path
    missed something (counted as `missed`); those writes publish their changes, so the dependents follow. No model call
    for an unchanged input (recorded decisions)."""
    from . import episodic, flows, periods
    r_f = flows.tick()
    missed = sum(int(v.get("changed", 0)) + int(v.get("retracted", 0)) for v in r_f.values() if isinstance(v, dict))
    r_p = episodic.plans()
    r_e = episodic.build()
    from . import search
    stale = search.stale_derived()
    with connection() as conn:
        for k in periods.stale_keys(conn):
            periods.mark_key(conn, k, reason="reconcile")
        for item_id in stale:                 # index chunks that no longer match their item
            processing.mark(conn, "search.reindex", item_id, reason="reconcile", settle=0)
    missed += len(stale)
    processing.count("assimilation.reconcile", keys=1, changed=missed)
    if missed:
        log.warning("reconciliation found %s changes the events had not produced", missed)
    return {"flows": r_f, "missed": missed, "stale_index": len(stale), "plans": r_p, "episodes": {k: v for k, v in r_e.items() if v},
            "runs": reconcile_runs()}


def reconcile_runs() -> dict:
    """The Run Plane's deadlines (socle A3/A4): runs that never received an end are closed as abandoned, objectives idle
    too long are suspended (never lost), and the episodes a detached builder missed are built (bounded per pass). Each
    step stands alone: a failure is logged and counted, the others still run."""
    from . import episodes, runs
    out: dict = {}
    for name, fn in (("abandoned", runs.sweep), ("episodes", lambda: len(episodes.pending()))):
        try:
            out[name] = fn()
        except Exception as exc:
            log.exception("run plane reconciliation: %s failed", name)
            out[name] = f"error: {type(exc).__name__}"
    processing.count("assimilation.reconcile_runs", keys=1,
                     changed=sum(v for v in out.values() if isinstance(v, int)))
    return out


def run(stop: threading.Event | None = None) -> None:
    """The consumer loop (a thread of walter-memory-pipeline): catch up, then LISTEN; after each wake-up and at least
    every minute, route new events and work the due keys (the deadlines). Reconciliation every RECONCILE_S."""
    c = bus.Consumer(CONSUMER, TYPES, batch=500, settle=1.0)
    last = {"reconcile": time.monotonic()}

    def idle():
        if engine() != "events":
            return
        w = work()
        if any(v.get("keys") for v in w.values()):
            log.info("assimilation %s", {k: v for k, v in w.items() if v.get("keys")})
        if time.monotonic() - last["reconcile"] >= RECONCILE_S:
            last["reconcile"] = time.monotonic()
            try:
                log.info("reconcile %s", reconcile())
            except Exception:
                log.exception("reconciliation failed")

    c.run(route, idle=idle, idle_every=0.0, batch=True)


def step(now: datetime | None = None, rounds: int = 10) -> dict:
    """Synchronous drain + work until quiet (tests, CLI): what the service does continuously."""
    c = bus.Consumer(CONSUMER, TYPES, batch=500)
    total: dict[str, dict] = {}
    for _ in range(rounds):
        routed = c.drain_batch(route)
        w = work(now)
        for k, v in w.items():
            t = total.setdefault(k, {"keys": 0, "changed": 0, "errors": 0})
            for f in t:
                t[f] += v.get(f, 0)
        if not routed and not any(v.get("keys") for v in w.values()):
            break
    return total
