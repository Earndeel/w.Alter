"""Walter Engine — the tool registry (2026-11-17).

One registry per engine: every tool the model can call, whatever its source (the engine's own: shell, files, jobs,
persistent Python, sub-agents; the Walter MCP server's: memory, skills, vault, browser…). A call goes through ONE
path, `Registry.execute`, whoever makes it (the model directly, Python's `await tools.x()`, a sub-agent): Walter's
policy (never-list, door preset, child ≤ parent, disclosure check, approval), the run's context, the journal and the
measurements apply the same way. Tools declare whether they may run beside others (`parallel`) or one at a time
(`exclusive`, the default for anything that writes or executes).

Lot 3e (2026-11-26): every tool has a capability declaration (`spec`: effects, concurrency, references,
idempotency), the same vocabulary as the module contracts (`walter_platform.capabilities`). A Walter tool's comes
from its module's contract; the engine's own tools declare theirs here (`NATIVE_SPECS`), next to their code.
A call on a shared resource (a file, a sub-agent, a job, a Python kernel) holds that resource's lock while it runs,
whichever door, agent or session makes it (`Registry.locks`); Walter tools are locked by the MCP server itself,
across every client process.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .. import config

log = logging.getLogger("walter_engine.tools")


def capabilities():
    """walter_platform.capabilities of the core this engine belongs to (shared with the MCP server)."""
    import sys
    if str(config.CORE_ROOT) not in sys.path:
        sys.path.insert(0, str(config.CORE_ROOT))
    from walter_platform import capabilities as caps
    return caps


@dataclass
class Result:
    content: str
    is_error: bool = False
    value: Any = None                 # a structured value for Python callers (`await tools.x()` returns it)
    meta: dict = field(default_factory=dict)


@dataclass
class Exec:
    """Who calls, for what, under which run: handed to every tool."""
    engine: Any
    agent: Any                        # engine.Agent (session, door, depth, run)
    call_id: str
    name: str
    cancel: asyncio.Event
    turn: int | None = None
    step: int | None = None
    parent_call: str | None = None    # a Python cell's call id for calls made from Python
    via: str = "model"                # model | python | api


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[dict, Exec], Awaitable[Result | str | Any]]
    parallel: bool = False
    source: str = "engine"            # engine | mcp:walter
    hidden: bool = False              # reachable from Python only (not offered to the model)
    spec: dict | None = None          # capability declaration (lot 3e); None = undeclared (effectful, serial)
    module: str | None = None         # the module that owns it (its contract declares it); engine tools: core

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": self.parameters}}


def clip(text: str, limit: int, *, head_ratio: float = 0.4) -> str:
    """Head and tail of a long text (the middle is what the model needs least), the omission said."""
    if len(text) <= limit:
        return text
    head = int(limit * head_ratio)
    tail = limit - head
    return f"{text[:head]}\n… [{len(text) - limit} caractères omis] …\n{text[-tail:]}"


def obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


# The engine's own tools: what each one does to the world and what it shares (same vocabulary as the module
# contracts). `parallel` in a model batch stays the Tool's own flag; a resource is locked whatever the door.
_ANY = ["local_write", "external_state", "outgoing", "cost"]
NATIVE_SPECS = {
    "bash": {"effects": _ANY, "concurrency": "serial", "idempotency": "none"},
    "read": {"effects": ["none"], "concurrency": "parallel", "consumes": ["file"]},
    "read_image": {"effects": ["none"], "concurrency": "serial", "consumes": ["file"]},
    "write": {"effects": ["local_write"], "concurrency": {"resource": "file", "key": "file_path"},
              "produces": ["file"], "idempotency": "natural"},
    "edit": {"effects": ["local_write"], "concurrency": {"resource": "file", "key": "file_path"},
             "consumes": ["file"], "produces": ["file"], "idempotency": "none"},
    "glob": {"effects": ["none"], "concurrency": "parallel", "produces": ["file"]},
    "grep": {"effects": ["none"], "concurrency": "parallel", "produces": ["file"]},
    "job_output": {"effects": ["none"], "concurrency": "parallel", "consumes": ["job"]},
    "job_kill": {"effects": ["external_state"], "concurrency": {"resource": "job", "key": "job_id"},
                 "consumes": ["job"], "idempotency": "natural"},
    "job_list": {"effects": ["none"], "concurrency": "parallel", "produces": ["job"]},
    "present": {"effects": ["record"], "concurrency": "serial", "consumes": ["file"], "idempotency": "none"},
    "ask_user_question": {"effects": ["none"], "concurrency": "parallel"},
    "context_recover": {"effects": ["none"], "concurrency": "parallel", "consumes": ["call"]},
    "subagent": {"effects": ["cost"], "concurrency": "serial", "produces": ["agent", "job"], "idempotency": "none"},
    "send_message": {"effects": ["cost"], "concurrency": {"resource": "agent", "key": "agent_id"},
                     "consumes": ["agent"], "idempotency": "none"},
    "interrupt_agent": {"effects": ["external_state"], "concurrency": {"resource": "agent", "key": "agent_id"},
                        "consumes": ["agent"], "idempotency": "natural"},
    "list_agents": {"effects": ["none"], "concurrency": "parallel", "produces": ["agent"]},
    # one persistent kernel per conversation: two cells of the same kernel never interleave
    "python": {"effects": _ANY, "concurrency": {"resource": "python-kernel", "key": "$session"}, "idempotency": "none"},
}


def discovery():
    """walter_platform.discovery (core's library): the one capability search, shared with every door."""
    capabilities()                                       # puts the core library on the path
    from walter_platform import discovery as d
    return d


class Registry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}
        self.exclusive = asyncio.Lock()
        self.locks = capabilities().ResourceLocks()      # in-process: every agent, session and door of the engine

    def add(self, tool: Tool) -> None:
        if tool.source == "engine":
            if tool.spec is None:
                tool.spec = NATIVE_SPECS.get(tool.name)
            tool.module = tool.module or "core"
        self.tools[tool.name] = tool

    def spec(self, name: str) -> dict:
        t = self.tools.get(name)
        caps = capabilities()
        return {**caps.DEFAULT_SPEC, **(t.spec or {})} if t else dict(caps.DEFAULT_SPEC)

    def _searchable(self) -> list[Tool]:
        return [t for n, t in sorted(self.tools.items()) if n != "python"]

    def _index(self):
        """The search index over the current tools, rebuilt when a tool, its description, its declaration or the
        generated intents change (cheap: ~25 ms for 60 tools)."""
        d = discovery()
        tools = self._searchable()
        try:
            stamp = d.cards_path().stat().st_mtime_ns
        except OSError:
            stamp = None
        key = (stamp, tuple((t.name, t.description, t.module, json.dumps(t.spec, sort_keys=True, default=str))
                            for t in tools))
        cached = getattr(self, "_search_cache", None)
        if cached and cached[0] == key:
            return cached[1]
        texts = getattr(self, "_module_texts", None)
        if texts is None:
            try:
                texts = d.module_texts()
            except Exception as e:  # noqa: BLE001 — discovery degrades to the tools' own text
                log.warning("module presentations unreadable for discovery: %s", e)
                texts = {}
            self._module_texts = texts
        idx = d.Index([self._entry(t) for t in tools], texts, d.load_intents())
        self._search_cache = (key, idx)
        return idx

    def _entry(self, t: Tool) -> dict:
        return {"name": t.name, "description": t.description, "parameters": t.parameters, "module": t.module,
                "spec": {**capabilities().DEFAULT_SPEC, **(t.spec or {})}}

    def remove_source(self, source: str) -> None:
        for name in [n for n, t in self.tools.items() if t.source == source]:
            del self.tools[name]

    def schemas(self, *, exclude: set[str] | None = None) -> list[dict]:
        return [t.schema() for t in self.tools.values() if not t.hidden and not (exclude and t.name in exclude)]

    def names(self) -> list[str]:
        return sorted(self.tools)

    def search(self, query: str, limit: int = 8) -> list[dict]:
        """Discovery for `await tools.search("…")`: BM25 over each tool's card, derived from its description, its
        module's presentation, its declaration and the intents generated from them (walter_platform.discovery).
        Each row: name, description, module, effects, score."""
        return self._index().search(str(query or ""), limit)

    def describe(self, name: str) -> dict:
        """A tool's whole contract: description, parameters, owner, effects, concurrency, references, returns."""
        t = self.tools.get(name)
        if not t:
            raise KeyError(f"no tool named {name}; await tools.search(\"…\")")
        return capabilities().describe_record(t.name, t.description, t.parameters,
                                              {**self.spec(name), "module": t.module})

    def catalog(self, module: str = "") -> dict:
        """Every tool reachable from Python, by owner, with its one-line summary and declared effects; the modules
        with their D1 line. `module` keeps one owner."""
        caps = capabilities()
        rows = []
        for t in self._searchable():
            if module and t.module != module:
                continue
            spec = self.spec(t.name)
            rows.append({"name": t.name, "module": t.module, "summary": caps.summary(t.description)[:240],
                         "effects": spec.get("effects"), "concurrency": spec.get("concurrency"),
                         "offered_to_model": not t.hidden})
        mods = sorted({r["module"] for r in rows if r["module"]})
        texts = getattr(self, "_module_texts", None) or {}
        return {"tools": rows, "modules": [{"module": m, "summary": texts.get(f"{m}:d1", "")} for m in mods]}


def parse_args(raw: Any) -> tuple[dict, str | None]:
    """A model's arguments string → dict, or an explanation the model can act on."""
    if isinstance(raw, dict):
        return raw, None
    if raw is None or raw == "":
        return {}, None
    try:
        v = json.loads(raw)
    except ValueError as e:
        return {}, f"arguments are not valid JSON ({e.msg} at {e.pos}); send one JSON object"
    if not isinstance(v, dict):
        return {}, "arguments must be one JSON object"
    return v, None


def as_result(value: Any) -> Result:
    if isinstance(value, Result):
        return value
    if isinstance(value, str):
        return Result(value, value=value)
    try:
        return Result(json.dumps(value, ensure_ascii=False, default=str), value=value)
    except (TypeError, ValueError):
        return Result(str(value), value=value)


def elapsed_ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
