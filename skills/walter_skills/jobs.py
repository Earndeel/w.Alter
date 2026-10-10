"""The nightly graph — small idempotent steps; one failing step never blocks the others; results in the registry.

sync Hermes → cards → catalog → implicit labels → judge sample → drafts from sessions → curation (also judges the
drafts) → cards of what curation changed → train + promote → domain map. The service hot-reloads by itself.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from . import cards, curation, domains, hermes_sync, learning, registry, store


def catalog() -> int:
    have = registry.cards()
    rows = []
    for s in store.iter_skills(include_archived=True, include_drafts=True):
        rows.append({"name": s.name, "state": s.state, "domain": s.domain, "owner": s.meta.get("owner"),
                     "origin": s.meta.get("origin"), "description": s.description[:2000],
                     "summary": (have.get(s.name) or {}).get("summary"), "path": str(s.path),
                     "content_sha": store.tree_hash(s.path), "card_sha": (have.get(s.name) or {}).get("sha"),
                     "meta": json.dumps(s.meta, default=str)})
    return registry.refresh_catalog(rows)


def curation_always_active() -> dict:
    """Operators that are safe to apply on master even during the shadow period (drafts: judged one by one)."""
    from . import config
    ops = set(config.get("curation").get("always_active", []))
    return curation.run(apply=True, only=ops)["summary"] if ops else {}


def curation_rest() -> dict:
    from . import config
    ops = {op.name for op in curation.OPERATORS} - set(config.get("curation").get("always_active", []))
    return curation.run(only=ops)["summary"]


QUICK = [  # every 15 minutes: what agents and Hermes just changed goes live within minutes, judged
    ("sync", lambda: {k: (v if isinstance(v, int) else len(v)) for k, v in hermes_sync.sync().items()}),
    ("drafts", curation_always_active),
    ("cards", cards.refresh),
    ("catalog", catalog),
]

STEPS = [
    ("sync", lambda: {k: (v if isinstance(v, int) else len(v)) for k, v in hermes_sync.sync().items()}),
    ("cards", cards.refresh),
    ("catalog", catalog),
    ("implicit", learning.implicit),
    ("judge", learning.judge),
    ("sessions", learning.drafts_from_sessions),
    ("drafts", curation_always_active),
    ("curation", curation_rest),
    ("cards_after", cards.refresh),
    ("train", learning.train_and_promote),
    ("domain_map", lambda: len(domains.build())),
]


def nightly(only: set[str] | None = None, steps=None, key: str = "nightly") -> dict:
    started = datetime.now(timezone.utc).isoformat()
    out = {}
    for name, fn in steps or STEPS:
        if only and name not in only:
            continue
        t0 = time.time()
        try:
            out[name] = {"ok": True, "result": fn(), "s": round(time.time() - t0)}
        except Exception as e:
            out[name] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}", "s": round(time.time() - t0)}
    state = {"started": started, "finished": datetime.now(timezone.utc).isoformat(),
             "failed": [k for k, v in out.items() if not v["ok"]], "steps": out}
    registry.set_state(key, state)
    registry.ledger("jobs", key, None, None, {"failed": state["failed"], "seconds": {k: v["s"] for k, v in out.items()}})
    return state


def quick() -> dict:
    return nightly(steps=QUICK, key="quick")


def health() -> tuple[list[str], dict]:
    import urllib.request
    problems, m = [], {}
    try:
        with urllib.request.urlopen("http://127.0.0.1:8891/health", timeout=10) as r:  # noqa: S310
            m["service"] = json.loads(r.read())
            if m["service"].get("degraded"):
                problems.append("walter-skills service running on its local snapshot (registry unreachable at start)")
    except Exception as e:
        problems.append(f"walter-skills service down: {type(e).__name__}")
    try:
        n = registry.get_state("nightly") or {}
        if n.get("finished"):
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(n["finished"])).total_seconds() / 3600
            m["nightly_age_h"] = round(age, 1)
            if age > 30:
                problems.append(f"walter-skills nightly has not run for {age:.0f} h")
        if n.get("failed"):
            problems.append(f"walter-skills nightly steps failed: {', '.join(n['failed'])}")
        m["active_ranker"] = (registry.ranker() or {}).get("version")
        if not m["active_ranker"]:
            problems.append("no active ranker")
        have = registry.cards()
        stale = [s.name for s in store.iter_skills() if have.get(s.name, {}).get("sha") != store.tree_hash(s.path)]
        m["stale_cards"] = len(stale)
        if len(stale) > 10:
            problems.append(f"{len(stale)} skills have out-of-date trigger cards")
    except Exception as e:
        problems.append(f"walter-skills registry unreachable: {type(e).__name__}")
    drafts = [p for p in store.DRAFTS.iterdir() if p.is_dir()] if store.DRAFTS.exists() else []
    m["drafts_pending"] = len(drafts)
    if len(drafts) > 40:
        problems.append(f"{len(drafts)} skill drafts waiting")
    return problems, m
