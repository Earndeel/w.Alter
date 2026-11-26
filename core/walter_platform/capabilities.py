"""Walter's capabilities as one generated view (lot 3e, owner 2026-11-26).

Every module stays the owner of its capabilities: the code (the tool and its description), the contract
(`presentation.tools` = ownership, `presentation.capabilities` = how the capability chains and runs) and the logic.
This library only READS those declarations and gives every door the same rules:

- what a capability declares: `effects` (none | local_write | record | outgoing | cost | external_state),
  `concurrency` (parallel | serial | a shared resource), `produces` / `consumes` (typed reference kinds),
  `idempotency` (natural | key:<argument> | none), `returns` (output schema), `errors` (codes);
- argument validation against a tool's own schema (missing AND unknown arguments, with the schema in the error);
- resource locks: a call on a resource another call uses waits for it, whichever tool, session, agent or process
  holds it (`ResourceLocks`, in-process + `flock` across processes);
- the generic door `walter_call` (its schema, its listing, its describe record), one implementation for the Engine
  and for the MCP server's door to external clients.

Declarations are additive: an undeclared tool keeps today's behaviour (`effects` unknown → treated as effectful,
`concurrency` serial). Security stays with the policy (walter_security): nothing here grants or relaxes a permission;
`effects` is a declaration that a test checks against the policy classes, never a permission.
"""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path

EFFECTS = ("none", "local_write", "record", "outgoing", "cost", "external_state")
REF_KINDS = ("event", "derived", "object", "log", "entity", "thread", "task", "skill", "secret", "agent", "call", "job",
             "view", "file", "browser_session", "device_session", "plan", "card")
ERROR_CODES = ("invalid_request", "not_found", "permission_denied", "dependency_unavailable", "deadline_exceeded",
               "budget_exceeded", "conflict", "outcome_unknown", "internal_error")
SPEC_KEYS = {"effects", "concurrency", "produces", "consumes", "idempotency", "returns", "errors"}
_ARG = re.compile(r"[a-z_][a-z0-9_]{0,63}\Z")
_RESOURCE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
DEFAULT_SPEC = {"effects": ["unknown"], "concurrency": "serial", "produces": [], "consumes": [], "idempotency": "none"}
LOCK_DIR = Path(os.environ.get("WALTER_LOCK_DIR", "/run/walter/locks"))


def _fail(message):
    raise ValueError(message)


def validate_spec(tool: str, spec) -> dict:
    """A module's declaration of one capability (contracts.py calls this for presentation.capabilities)."""
    if not isinstance(spec, dict) or not set(spec) <= SPEC_KEYS:
        _fail(f"invalid capability declaration for {tool}")
    effects = spec.get("effects", [])
    if not isinstance(effects, list) or not effects or any(e not in EFFECTS for e in effects) \
            or ("none" in effects and len(effects) > 1):
        _fail(f"{tool}: effects = a non-empty list of {', '.join(EFFECTS)} ('none' alone)")
    c = spec.get("concurrency", "serial")
    if isinstance(c, dict):
        if not set(c) <= {"resource", "key", "key_default"} or not _RESOURCE.fullmatch(str(c.get("resource", ""))):
            _fail(f"{tool}: concurrency resource = {{resource, key?, key_default?}}")
        if "key" in c and not (_ARG.fullmatch(str(c["key"])) or c["key"] == "$session"):
            _fail(f"{tool}: concurrency key = an argument name or $session")
        if "key_default" in c and not isinstance(c["key_default"], str):
            _fail(f"{tool}: concurrency key_default = a format string of the arguments")
    elif c not in ("parallel", "serial"):
        _fail(f"{tool}: concurrency = parallel | serial | {{resource, key}}")
    for k in ("produces", "consumes"):
        v = spec.get(k, [])
        if not isinstance(v, list) or any(x not in REF_KINDS for x in v):
            _fail(f"{tool}: {k} = reference kinds among {', '.join(REF_KINDS)}")
    idem = spec.get("idempotency", "none")
    if not (idem in ("natural", "none") or (isinstance(idem, str) and idem.startswith("key:") and _ARG.fullmatch(idem[4:]))):
        _fail(f"{tool}: idempotency = natural | none | key:<argument>")
    if "returns" in spec and not (isinstance(spec["returns"], dict) and spec["returns"].get("type")):
        _fail(f"{tool}: returns = a JSON schema with a type")
    errors = spec.get("errors", [])
    if not isinstance(errors, list) or any(e not in ERROR_CODES for e in errors):
        _fail(f"{tool}: errors among {', '.join(ERROR_CODES)}")
    return spec


# ── the generated view ────────────────────────────────────────────────────────────────────────────────────────────
def declarations(registry: dict | None = None) -> dict[str, dict]:
    """tool → its declaration + `module` (its owner), for every tool a module presents. Generated each time from the
    compiled registry (itself compiled from the module contracts): never a list kept by hand."""
    if registry is None:
        from .registry import load
        registry = load()
    out: dict[str, dict] = {}
    for m in registry.get("modules", []):
        p = m.get("presentation") if isinstance(m.get("presentation"), dict) else {}
        caps = p.get("capabilities") or {}
        for tool in p.get("tools") or []:
            out[tool] = {**DEFAULT_SPEC, **(caps.get(tool) or {}), "module": m["id"],
                         "declared": tool in caps}
    return out


def spec_of(decls: dict, tool: str) -> dict:
    return decls.get(tool) or {**DEFAULT_SPEC, "module": None, "declared": False}


def effectful(spec: dict) -> bool:
    return spec.get("effects") != ["none"]


# ── arguments ─────────────────────────────────────────────────────────────────────────────────────────────────────
def check_arguments(schema: dict | None, args: dict) -> dict:
    """{'missing': [...], 'unknown': [...]} against the tool's own input schema. An empty or absent value of a required
    argument is missing (a tool never runs on a guessed default). An argument the schema does not name is unknown
    unless the schema allows extra properties."""
    schema = schema or {}
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    missing = [k for k in required if args.get(k) in (None, "")]
    open_schema = schema.get("additionalProperties") is True or not props and schema.get("additionalProperties") is not False
    unknown = [] if open_schema else sorted(k for k in args if k not in props)
    return {"missing": missing, "unknown": unknown}


def argument_error(tool: str, schema: dict | None, problems: dict) -> dict:
    parts = []
    if problems.get("missing"):
        parts.append("missing required argument(s) " + ", ".join(problems["missing"]))
    if problems.get("unknown"):
        parts.append("unknown argument(s) " + ", ".join(problems["unknown"]))
    return error("invalid_request", f"{tool}: " + "; ".join(parts), tool=tool,
                 parameters=(schema or {}).get("properties") or {}, required=(schema or {}).get("required") or [])


def error(code: str, message: str, **extra) -> dict:
    if code not in ERROR_CODES:
        code = "internal_error"
    return {"ok": False, "error": code, "message": message, **extra}


# ── resource locks ────────────────────────────────────────────────────────────────────────────────────────────────
def lock_key(spec: dict, args: dict, *, session: str | None = None) -> tuple[str, str] | None:
    """(resource, key) a call holds while it runs, or None. The key is the argument the declaration names (a browser
    session, a device, a file, a chat…); without that argument, `key_default` formats one from the arguments
    (browser_session's default session '<site>-me'); a declaration without key locks the whole resource."""
    c = spec.get("concurrency")
    if not isinstance(c, dict):
        return None
    resource = c["resource"]
    key_arg = c.get("key")
    if key_arg is None:
        return resource, "*"
    if key_arg == "$session":
        value = session or ""
    else:
        value = args.get(key_arg)
        value = "" if value is None else str(value)
    if not value and c.get("key_default"):
        try:
            value = c["key_default"].format(**{k: v for k, v in args.items() if isinstance(v, (str, int, float))})
        except (KeyError, IndexError, ValueError):
            value = ""
    if not value:
        return None             # no shared state named: nothing to protect (a public page read, no session)
    if key_arg in ("file_path", "path"):
        value = os.path.realpath(value)   # one file, whatever path names it
    return resource, value


class ResourceLocks:
    """One lock per (resource, key). In-process: an asyncio lock (every agent, sub-agent, Python cell and door of the
    process). Across processes (`interprocess=True`): an exclusive `flock` on a file of LOCK_DIR named by a hash of
    the key, released by the OS if the holder dies. A wait is cancellable (interruption, timeout of the caller)."""

    def __init__(self, *, interprocess: bool = False, lock_dir: Path | None = None):
        self.interprocess = interprocess
        self.lock_dir = Path(lock_dir or LOCK_DIR)
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self.holders: dict[tuple[str, str], str] = {}

    def _lock(self, key):
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        return lock

    @contextlib.asynccontextmanager
    async def hold(self, key: tuple[str, str] | None, holder: str = ""):
        if key is None:
            yield None
            return
        lock = self._lock(key)
        await lock.acquire()
        fh = None
        try:
            if self.interprocess:
                self.lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                name = hashlib.sha256(f"{key[0]}\0{key[1]}".encode()).hexdigest()[:32]
                fh = open(self.lock_dir / f"{key[0]}-{name}.lock", "a+")
                while True:
                    try:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        await asyncio.sleep(0.05)   # cancellable wait, never a thread stuck on a lock
            self.holders[key] = holder
            yield key
        finally:
            self.holders.pop(key, None)
            if fh is not None:
                with contextlib.suppress(OSError):
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                fh.close()
            lock.release()
            if not lock.locked() and not getattr(lock, "_waiters", None):
                self._locks.pop(key, None)


# ── the generic door ──────────────────────────────────────────────────────────────────────────────────────────────
WALTER_CALL = "walter_call"
WALTER_CALL_SCHEMA = {"type": "object", "properties": {
    "tool": {"type": "string", "description": "the Walter tool to reach (empty: list them)"},
    "arguments": {"type": "object", "description": "its arguments"},
    "describe": {"type": "boolean", "description": "true: its contract instead of running it"}},
    "required": [], "additionalProperties": False}
WALTER_CALL_DESCRIPTION = (
    "Reach a Walter tool that is not in your tool list: walter_call() lists them, walter_call(tool=NAME, "
    "describe=true) gives its contract (parameters, what it returns, effects, references it takes), "
    "walter_call(tool=NAME, arguments={…}) runs it under exactly the same rules as a direct call.")
NOT_THROUGH_WALTER_CALL = {WALTER_CALL, "python"}


def summary(description: str) -> str:
    return (description or "").strip().split("\n\n")[0].replace("\n", " ").strip()


def resolve_call(args: dict) -> dict:
    """What a walter_call asks: {'mode': 'list'} | {'mode': 'describe', 'tool'} | {'mode': 'run', 'tool',
    'arguments'} | {'mode': 'error', 'error': {...}}. Pure: the door that calls it applies its own pipeline."""
    unknown = sorted(set(args) - set(WALTER_CALL_SCHEMA["properties"]))
    if unknown:
        return {"mode": "error", "error": error("invalid_request", "walter_call takes tool, arguments, describe; "
                                                f"unknown: {', '.join(unknown)}")}
    tool = str(args.get("tool") or "").strip()
    if tool.startswith("mcp__walter__"):
        tool = tool.removeprefix("mcp__walter__")
    if not tool:
        return {"mode": "list"}
    if tool in NOT_THROUGH_WALTER_CALL:
        return {"mode": "error", "error": error("invalid_request", f"{tool} cannot be reached through walter_call")}
    if args.get("describe") is True:
        return {"mode": "describe", "tool": tool}
    arguments = args.get("arguments")
    if arguments is None:
        arguments = {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except ValueError:
            arguments = None
    if not isinstance(arguments, dict):
        return {"mode": "error", "error": error("invalid_request", "arguments must be one JSON object")}
    return {"mode": "run", "tool": tool, "arguments": arguments}


def listing(entries: dict[str, dict]) -> dict:
    """walter_call() without tool: name → one-line summary, with its owner, for the tools behind the door."""
    return {"tools": [{"name": n, "summary": summary(e.get("description") or "")[:240],
                       **({"module": e["module"]} if e.get("module") else {})} for n, e in sorted(entries.items())]}


def describe_record(name: str, description: str, parameters: dict | None, spec: dict | None = None) -> dict:
    """The contract of one tool, the same through every door (walter_call describe, Python tools.describe,
    the registry view)."""
    spec = spec or {}
    rec = {"name": name, "description": description, "parameters": parameters or {"type": "object", "properties": {}}}
    if spec.get("module"):
        rec["module"] = spec["module"]
    for k in ("effects", "concurrency", "produces", "consumes", "idempotency", "returns", "errors"):
        if spec.get(k) not in (None, [], ""):
            rec[k] = spec[k]
    return rec


def unknown_tool(tool: str, candidates: list[str]) -> dict:
    return error("not_found", f"no Walter tool named {tool}", candidates=candidates[:3],
                 hint="walter_call() lists the tools behind this door; tools.search(…) in Python")


def outcome_unknown(tool: str, spec: dict, why: str) -> dict:
    """An effectful call whose answer was lost (interrupted, timed out, connection lost): it may or may not have
    taken effect. Never retried by the door; the caller is told how to check, and whether a retry is safe."""
    idem = spec.get("idempotency") or "none"
    safe = ("replaying the same call is safe (idempotent)" if idem == "natural" else
            f"retrying with the same {idem[4:]} is safe" if idem.startswith("key:") else
            "check whether it took effect before calling it again")
    return error("outcome_unknown", f"{tool}: {why}; the operation may have taken effect — {safe}", tool=tool,
                 idempotency=idem)


# ── progressive pagination: one opaque `cursor` beside the legacy offset/next fields ─────────────────────────────
def page_cursor(read: str, offset) -> str | None:
    """The cursor that continues `read` at `offset` (None at the end). Same encoding as Walter Memory's cursors."""
    if offset in (None, "", 0) or not isinstance(offset, int) or offset < 0:
        return None
    raw = json.dumps({"r": read, "p": {"offset": offset}}, separators=(",", ":")).encode()
    import base64
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def page_offset(read: str, cursor: str) -> int:
    """The offset a cursor of `read` carries. A cursor of another read, or carrying anything else than the page
    position, is refused (ValueError): it never changes a filter, a scope or a permission."""
    import base64
    try:
        doc = json.loads(base64.urlsafe_b64decode(str(cursor).strip() + "=" * (-len(str(cursor).strip()) % 4)))
    except (ValueError, TypeError):
        raise ValueError("cursor is not one this read issued; pass the `cursor` of its last answer as is") from None
    if not isinstance(doc, dict) or doc.get("r") != read or not isinstance(doc.get("p"), dict) or set(doc["p"]) != {"offset"}:
        raise ValueError(f"cursor was not issued by {read}")
    offset = doc["p"]["offset"]
    if not isinstance(offset, int) or offset < 0:
        raise ValueError("cursor is not one this read issued")
    return offset


def with_cursor(read: str, page):
    """Add `cursor` beside an answer's `next_offset` (kept: existing clients use it)."""
    if isinstance(page, dict) and page.get("next_offset") is not None:
        token = page_cursor(read, page["next_offset"])
        if token:
            page = {**page, "cursor": token}
    return page
