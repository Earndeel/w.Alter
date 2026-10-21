"""The source registry: collect every source into models.snapshots (a failing source keeps its last good snapshot), retention."""
from __future__ import annotations

from typing import Any

from walter_router.research.benchmarks.aa import source_aa, source_da, source_mm
from walter_router.research.benchmarks.aa_decision import source_aa_decision
from walter_router.research.benchmarks.aa_stt import source_aa_stt
from walter_router.research.benchmarks.agentset import source_agentset
from walter_router.research.benchmarks.arena import source_arena
from walter_router.research.benchmarks.bridgebench import source_bridgebench
from walter_router.research.benchmarks.mteb import source_mteb
from walter_router.research.prices.codex import source_codex
from walter_router.research.prices.declared import source_declared
from walter_router.research.prices.kie import source_kie
from walter_router.research.prices.openrouter import source_openrouter
from walter_router.research.prices.providers import source_hermes_providers

SOURCES = {"aa": source_aa, "aa_decision": source_aa_decision, "mm": source_mm, "da": source_da, "arena": source_arena, "bridgebench": source_bridgebench,
           "aa_stt": source_aa_stt, "agentset": source_agentset, "mteb": source_mteb,
           "openrouter": source_openrouter, "kie": source_kie, "codex": source_codex,
           "declared": source_declared, "hermes_providers": source_hermes_providers}


def collect_all(conn, store) -> dict[str, Any]:
    """Collect every source; a failing source is reported and the last good snapshot stays in use. `store(conn, kind,
    doc, fetched_at, url)` keeps the snapshot and its parsed rows (analysis.ingest.store)."""
    report: dict[str, Any] = {}
    for kind, fn in SOURCES.items():
        try:
            doc, fetched_at, url = fn()
            with conn.transaction():
                sid, new = store(conn, kind, doc, fetched_at, url)
            report[kind] = {"snapshot_id": sid, "new": new}
        except Exception as exc:  # noqa: BLE001 — one source must not stop the others
            report[kind] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return report


def prune(conn, keep_days: int = 30) -> int:
    """Delete snapshots older than keep_days, always keeping the latest one of each kind."""
    cur = conn.execute("""delete from models.snapshots s where fetched_at < now() - make_interval(days => %s)
                          and snapshot_id <> (select max(snapshot_id) from models.snapshots t where t.kind = s.kind)""",
                       (keep_days,))
    return cur.rowcount
