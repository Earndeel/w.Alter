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
            if r["threads"]:
                log.info("tick %s", r)
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
