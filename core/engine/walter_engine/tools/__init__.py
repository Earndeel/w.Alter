"""Walter Engine — the tool registry (2026-11-17).

One registry per engine: every tool the model can call, whatever its source (the engine's own: shell, files, jobs,
persistent Python, sub-agents; the Walter MCP server's: memory, skills, vault, browser…). A call goes through ONE
path, `Registry.execute`, whoever makes it (the model directly, Python's `await tools.x()`, a sub-agent): Walter's
policy (never-list, door preset, child ≤ parent, disclosure check, approval), the run's context, the journal and the
measurements apply the same way. Tools declare whether they may run beside others (`parallel`) or one at a time
(`exclusive`, the default for anything that writes or executes).
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


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


# French words of a discovery query → the English vocabulary the tools are described in (accents folded)
_FR = {"fichier": "file", "dossier": "directory", "repertoire": "directory", "lire": "read", "ecrire": "write",
       "modifier": "edit", "chercher": "search", "recherche": "search", "trouver": "find", "memoire": "memory",
       "souvenir": "memory", "navigateur": "browser", "page": "web", "internet": "web", "commande": "command",
       "executer": "run", "lancer": "run", "tache": "task", "travail": "job", "envoyer": "send", "message": "message",
       "personne": "person", "contact": "person", "agenda": "calendar", "calendrier": "calendar", "image": "image",
       "photo": "image", "secret": "secret", "mot": "password", "sous": "subagent", "agent": "agent",
       "deleguer": "delegate", "competence": "skill", "journal": "log", "coffre": "vault", "son": "audio",
       "vocal": "audio", "telegramme": "telegram", "courriel": "mail", "e-mail": "mail"}


def _fold(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(text or "").lower()) if not unicodedata.combining(c))


def _terms(query: str) -> list[tuple[str, ...]]:
    """Each word of a query with what else it may be written as: its stem (plural, conjugation) and, for a French
    word, the English word of the tool descriptions."""
    out = []
    for w in "".join(c if c.isalnum() or c in "_-" else " " for c in _fold(query)).split():
        if len(w) < 2:
            continue
        alts = {w, w[:-1] if len(w) > 4 and w.endswith("s") else w}
        stem = w.rstrip("s")
        for fr, en in _FR.items():
            if stem == fr or (len(stem) >= 5 and stem.startswith(fr[:5]) and len(fr) >= 5):
                alts.add(en)
        out.append(tuple(sorted(alts)))
    return out


class Registry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}
        self.exclusive = asyncio.Lock()

    def add(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def remove_source(self, source: str) -> None:
        for name in [n for n, t in self.tools.items() if t.source == source]:
            del self.tools[name]

    def schemas(self, *, exclude: set[str] | None = None) -> list[dict]:
        return [t.schema() for t in self.tools.values() if not t.hidden and not (exclude and t.name in exclude)]

    def names(self) -> list[str]:
        return sorted(self.tools)

    def search(self, query: str, limit: int = 8) -> list[dict]:
        """Discovery for `await tools.search("…")`: words of the query (French or English, accents and plurals
        ignored, a few French words also read as their English tool vocabulary) against names and descriptions."""
        words = _terms(query)
        scored = []
        for t in self.tools.values():
            if t.name == "python":
                continue
            n, d = _fold(t.name), _fold(t.description)
            score = sum(max((3 if v in n else 0) + (1 if v in d else 0) for v in alts) for alts in words) if words else 1
            if score > 0:
                scored.append((-score, t.name, t.description[:240]))
        scored.sort()
        return [{"name": n, "description": d} for _, n, d in scored[: max(1, min(50, int(limit or 8)))]]

    def describe(self, name: str) -> dict:
        t = self.tools.get(name)
        if not t:
            raise KeyError(f"no tool named {name}; await tools.search(\"…\")")
        return {"name": t.name, "description": t.description, "parameters": t.parameters}


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
