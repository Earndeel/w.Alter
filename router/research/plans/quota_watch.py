"""Subscription meters on the Walter bus (information only): after agent turns, re-read the meter of the plan that turn used.

Runs with the walter-memory interpreter (it owns the bus lib): `walter-router-quota.service`. A burst of turns gives
one reading (settle), each meter at most every MIN_AGE_S; an idle sweep every 30 min catches weekly resets and usage
from outside the VM (ChatGPT app, claude.ai).
"""
from __future__ import annotations

import logging

from walter_memory import bus

from walter_router.store import db
from walter_router.research.plans import subscriptions

# Which subscription a runtime's turns spend: Hermes and Codex CLI run on ChatGPT (Codex), Claude Code on Claude Pro.
SOURCE_SUBS = {"hermes": "openai-plus", "codex": "openai-plus", "claude_code": "anthropic-pro"}
MIN_AGE_S = {"openai-plus": 120, "anthropic-pro": 300}
log = logging.getLogger("walter.router.quota")


def react(events: list[dict]) -> dict:
    subs = sorted({SOURCE_SUBS[e["source"]] for e in events if e["source"] in SOURCE_SUBS})
    out = {}
    with db.connect() as conn:
        for sub_id in subs:
            out.update(subscriptions.refresh(conn, sub_id, min_age_s=MIN_AGE_S.get(sub_id, 120)))
        conn.commit()
    log.info("quota after %d events: %s", len(events), out)
    return out


def sweep() -> None:
    with db.connect() as conn:
        log.info("quota sweep: %s", subscriptions.refresh(conn, min_age_s=600))
        conn.commit()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sweep()
    bus.Consumer("walter-router-quota", ["turn.ended", "session.ended"], settle=20.0).run(
        react, idle=sweep, idle_every=1800, batch=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
