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
MEMORY_BUDGET = {"L3": {"profile": 0, "rules": 0, "working": 0, "people": 300, "knowledge": 600, "evidence": 300, "views": 200},
                 "L4": {"profile": 0, "rules": 0, "working": 0, "people": 600, "knowledge": 1200, "evidence": 800, "views": 300}}
RECORDS_BUDGET = {"profile": 0, "rules": 0, "working": 0, "people": 0, "records": 900, "knowledge": 0, "evidence": 0,
                  "views": 0}
STATE_BUDGET = {"rules": 350, "working": 1200}   # layer 2 (Memory V1 P1.1): every level but L0 without a thread
UNSURE_PLAN = 0.5               # below this plan confidence, the cheap records lookup is added (calibration 28/10)
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


def session_state(plan: ContextPlan, message: str, session_key: str | None) -> Block | None:
    """Layer 2, SessionState (Memory V1 P1.1): the owner's durable rules in force (always, stable) and the working
    state of this session's thread — interpreted decisions and constraints of the thread and of its subject in other
    runtimes, the owner's words not interpreted yet verbatim, the agent's plan. Rebuilt from Memory at each message, so
    a compression or another runtime loses nothing."""
    from walter_memory import context
    source, thread = None, None
    if session_key and session_key.count("/") >= 2:
        source, _, thread = session_key.split("/", 2)
        source = {"claude-code": "claude_code"}.get(source, source)
    budget = {k: 0 for k in ("profile", "people", "records", "knowledge", "evidence", "views")} | STATE_BUDGET
    r = context.get_context(message, budget=budget, include_profile=False,
                            session=(source, thread) if source and thread else None)
    if not r.get("text"):
        return None
    refs = [ref for s in (r.get("trace") or {}).get("sections", {}).values() for ref in (s.get("refs") or [])]
    return Block("session_state", 2, r["text"], sources=refs[:30])


def subject(plan: ContextPlan) -> Block | None:
    depth = SUBJECT_DEPTH.get(plan.level)
    key = plan.thread.id
    if not depth or not key or not key.startswith("subject:"):
        return None
    from walter_memory import views
    r = views.read({"depth": depth, "key": "g1:" + key, "max_tokens": 900})     # V1 view, rebuilt from knowledge
    if "error" in r:
        r = views.read({"depth": depth, "key": key, "max_tokens": 900})
    if "error" in r:
        return None
    key = r.get("key") or key
    return Block(f"subject:{r['depth']}", 3, f"Sujet {key} ({r['depth']}) :\n{r['content']}",
                 sources=[{"view": key, "version": r.get("version"), "stale": r.get("stale")}])


def _gets_memory(plan: ContextPlan) -> bool:
    return plan.level != "L0" and bool(MEMORY_BUDGET.get(plan.level) or (set(plan.domains) - {"projects"}))


def memory(plan: ContextPlan, message: str) -> Block | None:
    budget = MEMORY_BUDGET.get(plan.level)
    if not _gets_memory(plan):
        return None
    from walter_memory import context
    r = context.get_context(message, budget=budget or MEMORY_BUDGET["L3"], include_profile=False)
    if not r.get("text"):
        return None
    refs = [ref for s in (r.get("trace") or {}).get("sections", {}).values() for ref in (s.get("refs") or [])]
    return Block("memory", 4, r["text"], sources=refs[:20])


def records(plan: ContextPlan, message: str) -> Block | None:
    """The curated records (decisions register, owner rules) matching the message, when the plan gets no memory block
    but says the answer must be looked up, or is unsure of itself. Calibration 2026-10-28 (DSH trials): questions on
    Walter's own setup or the owner's decisions were planned L0 « tools suffice » with low confidence, and a model
    without tools then had nothing to answer from."""
    conf = ((plan.decision or {}).get("confidence") or {}).get("plan")
    if "search" not in plan.capabilities and not (conf is not None and conf < UNSURE_PLAN):
        return None
    from walter_memory import context
    r = context.get_context(message, budget=RECORDS_BUDGET, include_profile=False)
    if not r.get("text"):
        return None
    return Block("records", 4, r["text"], sources=(r.get("trace") or {}).get("sections", {}).get("records", {}).get("refs", []))


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
    """The blocks the plan asks for. L0: capabilities (+ records when unsure or a lookup is needed). Returns (blocks, notes on failed sources)."""
    steps = [("capabilities", lambda: capabilities(plan))]
    if plan.level != "L0":
        steps += [("board", board), ("session_state", lambda: session_state(plan, message, session_key)),
                  ("subject", lambda: subject(plan)), ("memory", lambda: memory(plan, message)),
                  ("recent", lambda: recent(session_key, native_history))]
    if not _gets_memory(plan):
        steps.append(("records", lambda: records(plan, message)))
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
