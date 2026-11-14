"""Memory generations (Memory V1 P1.0): which interpretations Walter reads, and the reversible switch g0 → g1.

g0 = pre-V1 interpretations (Hindsight, user_model_compiler, L3 v1, legacy subject views); g1 = V1 (extract2 from the V1
start, curated documents). Generations apply to derived knowledge and projections only; canonical events and objects
are the evidence of every generation and stay searchable.

  read_set(history=False)  generations read by default (core.generations.readable), or all of them for an explicit
                           history request; None when the switch [generations] enforce is off (P0 behaviour)
  status()                 volumes per generation, kind, status
  preview(query)           what memory_context would read after the switch, against today (no rerank: no cost)
  switch(to, confirm)      to becomes active and the only readable generation; the others archived (history only)
  rollback(confirm)        the previous active generation back, every generation readable again (today's state)
The switch is an owner decision: both refuse without confirm=True.

Read mode (organic.toml [generations] read, 2026-11-10): how Context reads the readable generations.
  "all"       every readable generation in one candidate pool (the behaviour before)
  "g1_first"  g1 is the memory; g0 only as a targeted fallback: its candidates enter the same single rerank, and a g0
              row reaches the context only when it ranks among the best `g0_gate` knowledge candidates of the union,
              at most `g0_slots` of them, never as a paraphrase of a g1 row already there
read_mode() returns the mode and its parameters; history requests always read everything.
"""
from __future__ import annotations

import time

from . import organic
from .db import connection

_cache: tuple[float, list[str] | None] = (0.0, None)


def read_set(history: bool = False) -> list[str] | None:
    global _cache
    if not organic.enabled("generations"):
        return None
    if history:
        with connection() as conn:
            return [r["generation"] for r in conn.execute("select generation from core.generations order by 1")]
    if time.monotonic() - _cache[0] > 30 or _cache[1] is None:
        with connection() as conn:
            gens = [r["generation"] for r in conn.execute(
                "select generation from core.generations where readable order by 1")]
        _cache = (time.monotonic(), gens)
    return _cache[1]


_mode_override: dict | None = None      # benches: simulate a read mode for one call


def read_mode() -> dict:
    if _mode_override is not None:
        return _mode_override
    g = organic.settings().get("generations", {})
    return {"read": g.get("read", "all"), "g0_gate": int(g.get("g0_gate", 6)), "g0_slots": int(g.get("g0_slots", 3)),
            "g0_candidates": int(g.get("g0_candidates", 60))}


def forget_cache() -> None:
    global _cache
    _cache = (0.0, None)


def active() -> str:
    with connection() as conn:
        return conn.execute("select generation from core.generations where status = 'active'").fetchone()["generation"]


def status() -> dict:
    with connection() as conn:
        gens = conn.execute("select * from core.generations order by generation").fetchall()
        derived = conn.execute("""select generation, derived_by, status, count(*) n from core.derived_items
                                  group by 1, 2, 3 order by 1, 4 desc""").fetchall()
        views = conn.execute("select generation, status, count(*) n from views.view group by 1, 2 order by 1").fetchall()
        chunks = conn.execute("""select coalesce(generation, 'evidence') generation, count(*) n from search.chunks
                                 group by 1 order by 1""").fetchall()
    return {"generations": gens, "read_set": read_set(), "derived": derived, "views": views, "index": chunks,
            "enforce": organic.enabled("generations")}


def preview(query: str) -> dict:
    """memory_context for `query` today and as it would be after a switch to g1 (rerank off for both: free)."""
    from . import context, search
    real = search._rerank
    search._rerank = lambda q, rows, limit, timeout=8: rows[:limit]
    try:
        global _cache
        now = context.get_context(query, include_profile=False)
        saved = _cache
        _cache = (time.monotonic(), ["g1"])
        try:
            after = context.get_context(query, include_profile=False)
        finally:
            _cache = saved
    finally:
        search._rerank = real

    def items(res):
        return res.get("trace", {}).get("items", [])
    return {"query": query, "today": {"tokens": len(now["text"]) // 4, "items": items(now)},
            "after_switch": {"tokens": len(after["text"]) // 4, "items": items(after)},
            "text_after_switch": after["text"]}


def switch(to: str = "g1", *, confirm: bool = False, note: str = "") -> dict:
    if not confirm:
        return {"refused": "a generation switch is the owner's decision: rerun with --confirm"}
    with connection() as conn:
        if not conn.execute("select 1 from core.generations where generation = %s", (to,)).fetchone():
            return {"refused": f"unknown generation {to}"}
        prev = conn.execute("select generation from core.generations where status = 'active'").fetchone()["generation"]
        conn.execute("""update core.generations set status = 'archived', readable = false,
                          note = coalesce(note || ' | ', '') || %s where generation <> %s""",
                     (f"archived by switch to {to} at {time.strftime('%Y-%m-%d %H:%M')}Z {note}", to))
        conn.execute("""update core.generations set status = 'active', readable = true, activated_at = now(),
                          note = coalesce(note || ' | ', '') || %s where generation = %s""",
                     (f"activated (previous: {prev}) {note}", to))
    forget_cache()
    return {"active": to, "previous": prev, "readable": read_set()}


def rollback(*, confirm: bool = False, to: str = "g0") -> dict:
    """Back to the pre-switch state: `to` active, every generation readable."""
    if not confirm:
        return {"refused": "rerun with --confirm"}
    with connection() as conn:
        conn.execute("update core.generations set status = 'candidate', readable = true where generation <> %s", (to,))
        conn.execute("""update core.generations set status = 'active', readable = true, activated_at = now(),
                          note = coalesce(note || ' | ', '') || 'rolled back' where generation = %s""", (to,))
    forget_cache()
    return {"active": to, "readable": read_set()}
