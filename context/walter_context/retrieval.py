"""retrieval: what the ContextPlan asks for, fetched from the modules that own it, as blocks (lot 4, step D).

Every source is reached through its public interface: Walter Memory's library (views, context: same process,
warm), the `walter present` command for module capabilities (core), walter_logs through Walter Memory's logs API.
A block knows its layer (stable → volatile), whether the host already shows it natively (Claude Code keeps its own
history: the recent exchanges are then counted, not injected) and its sources. Nothing here calls a cloud model
except Walter Memory's context assembly at L3/L4, which applies its own privacy rules (cloud-safe, rerank).
Fail-open per block: a source that fails gives no block and a note, never an exception.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass, field

from .plan import ContextPlan

# capability → module whose brief (M1) the model gets in full; every module's one line (M0) is always there
CAPABILITY_MODULES = {"skills": ["skills"], "search": ["memory"], "delegation": ["router"], "secrets": ["secrets"]}
DOMAIN_MODULES = {"relations": ["memory"], "agenda": ["memory"], "profile": ["memory"], "activities": ["memory"],
                  "decisions": ["memory"], "goals": ["memory"]}
SUBJECT_DEPTH = {"L0": None, "L1": "index", "L2": "overview", "L3": "synthesis", "L4": "synthesis"}
MEMORY_BUDGET = {"L3": {"profile": 0, "people": 300, "knowledge": 600, "evidence": 300},
                 "L4": {"profile": 0, "people": 600, "knowledge": 1200, "evidence": 800}}
BOARD_TOKENS = 350
RECENT_EXCHANGES = 3


@dataclass
class Block:
    id: str
    layer: int                  # 0 stable (session) … 5 volatile (this message)
    text: str
    injected: bool = True       # False: the host already shows it (counted for the comparison only)
    sources: list = field(default_factory=list)
    ms: float = 0.0

    @property
    def tokens(self) -> int:
        return len(self.text) // 4 + 1 if self.text else 0

    def summary(self) -> dict:
        return {**{k: v for k, v in asdict(self).items() if k != "text"}, "tokens": self.tokens}


_CAP_CACHE: dict[tuple, tuple[float, str, list]] = {}


def capabilities(plan: ContextPlan, ttl: float = 600) -> Block | None:
    """M0 of every module + M1 of the modules the plan needs (session layer: changes rarely, cached)."""
    m1 = sorted({m for c in plan.capabilities for m in CAPABILITY_MODULES.get(c, [])} |
                {m for d in plan.domains for m in DOMAIN_MODULES.get(d, [])})
    key = tuple(m1)
    hit = _CAP_CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return Block("capabilities", 0, hit[1], sources=hit[2])
    args = ["walter", "present", "notes", "--form", "m0"] + (["--m1", ",".join(m1)] if m1 else [])
    out = json.loads(subprocess.run(args, capture_output=True, text=True, timeout=20).stdout)
    notes = out.get("notes") or []
    text = "\n\n".join(n["content"].strip() for n in notes if n.get("content"))
    ids = [n.get("id") for n in notes]
    _CAP_CACHE[key] = (time.time(), text, ids)
    return Block("capabilities", 0, text, sources=ids)


def board() -> Block | None:
    """The active subjects, one line each (changes when a subject changes state)."""
    from walter_memory import views
    r = views.read({"depth": "index", "domain": "projects", "horizon": "medium", "max_tokens": BOARD_TOKENS})
    if not r.get("content"):
        return None
    return Block("subjects_board", 1, "Sujets en cours (un par ligne) :\n" + r["content"], sources=r.get("views", []))


def subject(plan: ContextPlan) -> Block | None:
    depth = SUBJECT_DEPTH.get(plan.level)
    key = plan.thread.id
    if not depth or not key or not key.startswith("subject:"):
        return None
    from walter_memory import views
    r = views.read({"depth": depth, "key": key, "max_tokens": 900})
    if "error" in r:
        return None
    return Block(f"subject:{r['depth']}", 3, f"Sujet {key} ({r['depth']}) :\n{r['content']}",
                 sources=[{"view": key, "version": r.get("version"), "stale": r.get("stale")}])


def memory(plan: ContextPlan, message: str) -> Block | None:
    budget = MEMORY_BUDGET.get(plan.level)
    if not budget and not (set(plan.domains) - {"projects"}):
        return None
    from walter_memory import context
    r = context.get_context(message, budget=budget or MEMORY_BUDGET["L3"], include_profile=False)
    if not r.get("text"):
        return None
    refs = [ref for s in (r.get("trace") or {}).get("sections", {}).values() for ref in (s.get("refs") or [])]
    return Block("memory", 4, r["text"], sources=refs[:20])


def recent(session_key: str | None, native: bool) -> Block | None:
    """The last exchanges of the channel (the safety net measured 21/10). A host with native history already shows
    them: counted, not injected."""
    if not session_key:
        return None
    from walter_memory import logs
    from walter_memory.db import connection
    with connection() as conn:
        rows = logs.search(conn, "", session=session_key, types=["user/message", "assistant/message"], limit=12,
                           max_privacy="cloud_allowed")
    rows = rows if isinstance(rows, list) else rows.get("results", [])
    lines = [f"{'Owner' if r.get('type') == 'user/message' else 'Assistant'} : {(r.get('text') or r.get('snippet') or '')[:600]}"
             for r in reversed(rows[: RECENT_EXCHANGES * 2])]
    return Block("recent_exchanges", 5, "\n".join(lines), injected=not native, sources=[session_key]) if lines else None


def gather(plan: ContextPlan, message: str, *, session_key: str | None = None, native_history: bool = True) -> tuple[list[Block], list[str]]:
    """The blocks the plan asks for. L0: capabilities only. Returns (blocks, notes on failed sources)."""
    steps = [("capabilities", lambda: capabilities(plan))]
    if plan.level != "L0":
        steps += [("board", board), ("subject", lambda: subject(plan)), ("memory", lambda: memory(plan, message)),
                  ("recent", lambda: recent(session_key, native_history))]
    blocks, notes = [], []
    for name, step in steps:
        t0 = time.perf_counter()
        try:
            b = step()
        except Exception as exc:  # noqa: BLE001 — one source failing never drops the others
            notes.append(f"{name}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        if b is not None:
            b.ms = round((time.perf_counter() - t0) * 1000, 1)
            blocks.append(b)
    return blocks, notes
