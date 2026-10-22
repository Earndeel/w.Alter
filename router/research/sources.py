"""The source registry: collect every source into models.snapshots (a failing source keeps its last good snapshot), retention."""
from __future__ import annotations

import json
from typing import Any

from walter_router.research.benchmarks.aa import source_aa
from walter_router.research.benchmarks.aa_media import source_mm
from walter_router.research.benchmarks.design_arena import source_da
from walter_router.research.benchmarks.aa_decision import source_aa_decision
from walter_router.research.benchmarks.aa_evaluations import source_aa_eval
from walter_router.research.benchmarks.aa_stt import source_aa_stt
from walter_router.research.benchmarks.agentset import source_agentset
from walter_router.research.benchmarks.arena import source_arena
from walter_router.research.benchmarks.bridgebench import source_bridgebench
from walter_router.research.benchmarks.mteb import source_mteb
from walter_router.research.prices.codex import source_codex
from walter_router.research.prices.declared import source_declared
from walter_router.research.prices.kie import source_kie
from walter_router.research.prices.openrouter import source_openrouter
from walter_router.research.prices.openrouter_endpoints import source_or_endpoints
from walter_router.research.prices.providers import source_hermes_providers

SOURCES = {"aa": source_aa, "aa_eval": source_aa_eval, "aa_decision": source_aa_decision, "mm": source_mm, "da": source_da, "arena": source_arena, "bridgebench": source_bridgebench,
           "aa_stt": source_aa_stt, "agentset": source_agentset, "mteb": source_mteb,
           "openrouter": source_openrouter, "or_endpoints": source_or_endpoints, "kie": source_kie, "codex": source_codex,
           "declared": source_declared, "hermes_providers": source_hermes_providers}


# Sources shared by several categories can be read in parts; the parts are merged into the last snapshot.
PARTIAL = {"arena": "boards", "mm": "modules", "da": "categories"}


def merge(kind: str, old: dict, new: dict) -> dict:
    """The last complete document with the freshly read parts replacing theirs."""
    out = json.loads(json.dumps(old))
    key = PARTIAL[kind]
    out.setdefault(key, {}).update(new.get(key) or {})
    if kind == "arena":
        out["errors"] = {**{k: v for k, v in (old.get("errors") or {}).items() if k not in (new.get("boards") or {})},
                         **(new.get("errors") or {})}
    if kind == "da":
        out["agent_categories"] = {k[len("agents/"):]: v for k, v in out["categories"].items() if k.startswith("agents/")}
        out["registry"] = new.get("registry") or old.get("registry")
    out["generated_at"] = new.get("generated_at") or old.get("generated_at")
    return out


def collect_all(conn, store, only: list[str] | None = None, parts: dict[str, set | None] | None = None) -> dict[str, Any]:
    """Collect every source (or `only` these kinds, or `parts`: kind -> parts to read, None = whole source); a failing
    source is reported and the last good snapshot stays in use. `store(conn, kind, doc, fetched_at, url)` keeps the
    snapshot and its parsed rows (analysis.ingest.store)."""
    report: dict[str, Any] = {}
    for kind, fn in SOURCES.items():
        if (only and kind not in only) or (parts is not None and kind not in parts):
            continue
        want = (parts or {}).get(kind)
        try:
            if want and kind in PARTIAL:
                doc, fetched_at, url = fn(parts=set(want))
                last = conn.execute("""select raw from models.snapshots where kind = %s
                                       order by fetched_at desc, snapshot_id desc limit 1""", (kind,)).fetchone()
                if last:
                    doc = merge(kind, last["raw"], doc)
            else:
                doc, fetched_at, url = fn()
            with conn.transaction():
                sid, new = store(conn, kind, doc, fetched_at, url)
            report[kind] = {"snapshot_id": sid, "new": new, **({"parts": sorted(want)} if want and kind in PARTIAL else {})}
        except Exception as exc:  # noqa: BLE001 — one source must not stop the others
            report[kind] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return report


def prune(conn, keep_days: int = 30) -> int:
    """Delete snapshots older than keep_days, always keeping the latest one of each kind."""
    cur = conn.execute("""delete from models.snapshots s where fetched_at < now() - make_interval(days => %s)
                          and snapshot_id <> (select max(snapshot_id) from models.snapshots t where t.kind = s.kind)""",
                       (keep_days,))
    return cur.rowcount
