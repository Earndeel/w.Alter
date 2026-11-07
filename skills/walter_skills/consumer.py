"""walter-skills on the Walter bus — reacts to events, whatever runtime emitted them. No timer, no folder watching.

  consumer "walter-skills"           skill.proposed (write door: Claude Code, Codex, DSH, the learner…)
                                     skill.changed  (a runtime adapter: Hermes' on_skill_lifecycle hook…)
                                     → sync the changed skills of that runtime → judge the drafts → live + cards
  consumer "walter-skills-learning"  turn.ended / session.ended (every runtime's hooks)
                                     → implicit labels for those sessions (shown → opened, missed → searched)
                                     session.ended → the learner reads the session (may propose a skill → skill.proposed)

Two consumers, two cursors, two threads: a slow learner (the editor model, minutes) never delays a judgement.
Bursts are absorbed (settle) so five edits in a row cost one judgement. A missed event is not lost: each consumer
catches up from its cursor at start, and the hourly reconciliation (jobs.quick) sweeps what bypassed the bus
(a skill edited by hand, a Hermes update).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from walter_memory import bus

from . import cards, curation, hermes_sync, jobs, learning, registry, store

log = logging.getLogger("walter.skills.consumer")
INGEST_LAG_S = 30  # walter_logs ingests a finished turn within seconds (walter-logs-watch): give it this long


def react(events: list[dict]) -> dict:
    changed = {e["subject"] for e in events if e["type"] == "skill.changed" and e["source"] == "hermes" and e["subject"]}
    out: dict = {"events": len(events)}
    if changed:
        out["sync"] = {k: v for k, v in hermes_sync.sync(names=changed).items() if v}
    out["drafts"] = curation.run(apply=True, only={"drafts"})["summary"]["done"]
    out["cards"] = cards.refresh(list(store.iter_skills()))
    out["catalog"] = jobs.catalog()
    registry.ledger("bus", "react", None, None, {"changed": sorted(changed), "result": out,
                                                 "events": [e["id"] for e in events]})
    return out


def learn(events: list[dict]) -> dict:
    newest = max(e["at"] for e in events)
    wait = INGEST_LAG_S - (datetime.now(timezone.utc) - newest).total_seconds()
    if wait > 0:
        time.sleep(wait)
    sessions = sorted({e["subject"] for e in events if e["subject"]})
    ended = sorted({e["subject"] for e in events if e["type"] == "session.ended" and e["subject"]})
    out = {"sessions": len(sessions), "implicit": learning.implicit(session_ids=sessions) if sessions else {}}
    if ended:
        out["learner"] = learning.drafts_from_sessions(session_ids=ended, max_sessions=len(ended))
    if out["implicit"] or ended:
        registry.ledger("bus", "learn", None, None, {"sessions": sessions, "result": out})
    return out


CONSUMERS = [
    (bus.Consumer("walter-skills", ["skill.proposed", "skill.changed"], settle=10.0), react, jobs.quick),
    (bus.Consumer("walter-skills-learning", ["turn.ended", "session.ended"], settle=5.0), learn, None),
]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    store.DRAFTS.mkdir(exist_ok=True)
    threads = [threading.Thread(target=c.run, args=(handler,), kwargs={"idle": idle, "batch": True}, name=c.name,
                                daemon=True) for c, handler, idle in CONSUMERS]
    for t in threads:
        t.start()
    while all(t.is_alive() for t in threads):  # run() never returns; if a thread dies anyway, systemd restarts us
        time.sleep(30)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
