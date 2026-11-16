"""Walter Engine — persistent Python kernel (runs inside its bubble, as the unprivileged `walter-sandbox` user).

One kernel per agent session of the engine. Cells run in one persistent `__main__` namespace on one asyncio loop
(top-level `await`), so variables, imports and functions stay from one call to the next and survive a compaction of
the model's context. Every Walter tool is reached from Python through the engine (`await tools.<name>(...)`): the
call goes through the engine's tool registry, so Walter's policy, the logs and the approvals apply to it exactly as
to a direct call. Background work (`bash(..., background=True)`, `spawn(...)`) becomes an engine job: the agent is
woken when it ends. The namespace is snapshotted after each cell and restored when the kernel comes back (engine
restart, crash, idle stop).

Adapted from Unharnessed's `rlm` runtime (MIT, github.com/unharnessed-agent/Unharnessed, commit fe2cf28): cell
compilation with a trailing expression, top-level await, a private protocol fd with fd 1/2 pumped, interrupt by
cancellation then KeyboardInterrupt, dill snapshots with size caps. Walter's version drops what the engine already
owns (MCP client, goals, provider calls, Windows support) and adds the engine bridge (host calls, jobs, delegation).

Protocol `walter-1`, one JSON object per line. Host → kernel:
  {"type":"execute","id":ID,"code":str,"tools":[names]?}   {"type":"interrupt"}   {"type":"names","id":ID}
  {"type":"host_reply","id":HID,"ok":bool,"result":any,"error":str}   {"type":"job_kill","job":JID}
  {"type":"job_bound","job":JID,"engine":str|null,"error":str?}     (the engine's id of a background job)
  {"type":"snapshot","id":ID}   {"type":"restore","id":ID}   {"type":"shutdown"}
Kernel → host:
  {"event":"ready","protocol":"walter-1","python":"3.x"}
  {"event":"out","id":ID|null,"job":JID|null,"stream":"stdout"|"stderr","text":str}
  {"event":"result","id":ID,"text":str}
  {"event":"done","id":ID,"status":"ok"|"error"|"interrupted","error":{...}?,"names":[...]?,"jobs":[...]?}
  {"event":"host","id":HID,"cell":ID|null,"job":JID|null,"method":"tool"|"search"|"describe","params":{...}}
  {"event":"host_cancel","id":HID}
  {"event":"job","job":JID,"state":"start"|"completed"|"failed"|"killed","label":str,"result":str?}
"""
from __future__ import annotations

import ast
import asyncio
import contextvars
import importlib
import inspect
import itertools
import json
import linecache
import os
import pickle
import signal
import sys
import threading
import time
import traceback
import types
from typing import Any

PROTOCOL = "walter-1"
RESULT_CAP = 20_000            # characters of a trailing expression's repr
OUT_CHUNK = 16_000             # characters per `out` frame
CAPTURE_CAP = 1_000_000        # bytes kept per stream of one bash() call (the tail)
MAX_VAR_BYTES = 16 * 2**20     # snapshot caps (Unharnessed: 16 MiB per variable)
MAX_TOTAL_BYTES = 128 * 2**20
SNAPSHOT = os.environ.get("WALTER_KERNEL_SNAPSHOT") or os.path.join(os.getcwd(), ".snapshot", "state.pkl")

CELL: contextvars.ContextVar[str | None] = contextvars.ContextVar("cell", default=None)
JOB: contextvars.ContextVar[str | None] = contextvars.ContextVar("job", default=None)

_proto_lock = threading.Lock()
BIND_JOBS = os.environ.get("WALTER_KERNEL_BIND_JOBS") == "1"   # set by the engine plugin; protocol tests run without
BIND_WAIT_S = 3.0
_proto = None                  # the private protocol channel (a dup of the original fd 1)
_loop: asyncio.AbstractEventLoop | None = None
_queue: asyncio.Queue | None = None
_pending: dict[str, asyncio.Future] = {}
_host_ids = itertools.count(1)
_job_ids = itertools.count(1)
_cells = itertools.count(1)
_jobs: dict[str, "Job"] = {}
_cell_task: asyncio.Task | None = None
_cell_id: str | None = None
_stopping = False
NS: dict[str, Any] = {}
INJECTED: set[str] = set()


# ── protocol ────────────────────────────────────────────────────────────────────────────────────────────────────
def send(event: dict) -> None:
    line = json.dumps(event, ensure_ascii=False, default=str)
    with _proto_lock:
        _proto.write(line + "\n")
        _proto.flush()


class _Writer:
    """sys.stdout / sys.stderr: each write ships at once, tagged with the cell (or job) whose context wrote it."""

    def __init__(self, stream: str):
        self.stream = stream

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        for i in range(0, len(text), OUT_CHUNK):
            send({"event": "out", "id": CELL.get(), "job": JOB.get(), "stream": self.stream,
                  "text": text[i:i + OUT_CHUNK]})
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    @property
    def encoding(self) -> str:
        return "utf-8"


def _pump(fd: int, stream: str) -> None:
    """Raw fd 1/2 bytes (subprocesses, C extensions, os.write): shipped untagged, never mixed into the protocol."""
    with os.fdopen(fd, "rb", buffering=0) as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                return
            send({"event": "out", "id": _cell_id, "job": None, "stream": stream,
                  "text": chunk.decode("utf-8", "replace")})


# ── host calls: every Walter tool, through the engine ──────────────────────────────────────────────────────────
class ToolError(Exception):
    """A tool call the engine refused or that failed (Walter's policy, a missing tool, the tool's own error)."""


async def host(method: str, params: dict) -> Any:
    hid = f"h{next(_host_ids)}"
    fut = _loop.create_future()
    _pending[hid] = fut
    send({"event": "host", "id": hid, "cell": CELL.get(), "job": JOB.get(), "method": method, "params": params})
    try:
        reply = await fut
    except asyncio.CancelledError:
        send({"event": "host_cancel", "id": hid})
        raise
    finally:
        _pending.pop(hid, None)
    if not reply.get("ok"):
        raise ToolError(str(reply.get("error") or "tool call failed"))
    return reply.get("result")


class Tools:
    """The engine's tools, from Python. `await tools.search("mémoire")` finds them, `await tools.describe(name)` gives
    a tool's parameters, `await tools.<name>(**args)` or `await tools.call(name, **args)` runs one."""

    def __init__(self) -> None:
        self._names: list[str] = []

    def names(self) -> list[str]:
        return list(self._names)

    async def search(self, query: str, limit: int = 8) -> list[dict]:
        return await host("search", {"query": str(query), "limit": int(limit)})

    async def describe(self, name: str) -> dict:
        return await host("describe", {"name": str(name)})

    async def call(self, name: str, /, **arguments: Any) -> Any:
        return await host("tool", {"name": str(name), "arguments": arguments})

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        async def bound(**arguments: Any) -> Any:
            return await self.call(name, **arguments)
        bound.__name__ = name
        return bound

    def __dir__(self):
        return sorted(set(self._names) | {"search", "describe", "call", "names"})

    def __repr__(self) -> str:
        return f"<{len(self._names)} engine tools — await tools.search('…'), await tools.<name>(**args)>"

    def __reduce__(self):            # snapshots keep a reference, restored to the live object
        return (_live_tools, ())


def _live_tools() -> Tools:
    return NS.get("tools") or Tools()


# ── background jobs (engine jobs: the agent is woken when one ends) ────────────────────────────────────────────
class Job:
    """A background job. `id` is the engine's job id once the engine registered it (what job_output / job_kill and
    the wake-up notice name), the kernel's own key (`py<n>`) before or without an engine."""

    def __init__(self, jid: str, label: str, task: asyncio.Task):
        self.key, self.label, self.task, self.started = jid, label, task, time.time()
        self.engine_id: str | None = None
        self.refused: str | None = None
        self.bound = threading.Event()

    @property
    def id(self) -> str:
        return self.engine_id or self.key

    def done(self) -> bool:
        return self.task.done()

    def result(self) -> Any:
        return self.task.result()

    def kill(self) -> None:
        self.task.cancel()

    async def wait(self, timeout: float | None = None) -> Any:
        """Wait for the job (bounded by `timeout`), then its result. Prefer ending the turn: you are woken anyway."""
        return await asyncio.wait_for(asyncio.shield(self.task), timeout)

    def __await__(self):
        # `await bash(..., background=True)` / `await spawn(...)` hands the job back at once instead of blocking the
        # cell until it ends (the habit of awaiting bash() must not turn background work into foreground work)
        if False:   # pragma: no cover — makes this a generator
            yield
        return self

    def __repr__(self) -> str:
        state = "running" if not self.task.done() else ("killed" if self.task.cancelled() else
                                                        "failed" if self.task.exception() else "done")
        return f"<Job {self.id} {state}: {self.label}>"

    def __reduce__(self):
        return (str, (repr(self),))


def _summary(value: Any, cap: int = 4000, as_repr: bool = False) -> str:
    try:
        text = value if isinstance(value, str) and not as_repr else repr(value)
    except Exception as exc:  # noqa: BLE001
        text = f"<unrepresentable {type(value).__name__}: {exc}>"
    return text if len(text) <= cap else text[:cap] + f"… [{len(text) - cap} more characters]"


def spawn(work: Any, label: str | None = None) -> Job:
    """Run a coroutine (or an async callable) in the background, as an engine job. Returns a Job at once (awaiting
    the call too): `job.done()`, `await job.wait(timeout)`, `job.kill()`, `job.id` (the engine's id). When it ends the
    engine is told, and wakes the agent if it is idle."""
    if callable(work) and not inspect.isawaitable(work):
        work = work()
    if not inspect.isawaitable(work):
        raise TypeError("spawn() takes a coroutine or an async callable")
    jid = f"py{next(_job_ids)}"
    label = (label or getattr(work, "__qualname__", None) or "python job")[:200]

    async def runner():
        JOB.set(jid)
        return await work

    task = _loop.create_task(runner(), context=contextvars.copy_context())
    job = Job(jid, label, task)
    _jobs[jid] = job

    def finished(t: asyncio.Task) -> None:
        if t.cancelled():
            send({"event": "job", "job": jid, "state": "killed", "label": label})
        elif t.exception() is not None:
            exc = t.exception()
            send({"event": "job", "job": jid, "state": "failed", "label": label,
                  "result": f"{type(exc).__name__}: {exc}"})
        else:
            send({"event": "job", "job": jid, "state": "completed", "label": label, "result": _summary(t.result())})
    task.add_done_callback(finished)
    send({"event": "job", "job": jid, "state": "start", "label": label})
    if BIND_JOBS:   # the engine answers at once with its own id (read by the reader thread): the model sees that one
        job.bound.wait(BIND_WAIT_S)
        if job.refused:
            task.cancel()
            raise RuntimeError(f"background job refused by the engine: {job.refused}")
    return job


def jobs() -> list[Job]:
    return list(_jobs.values())


# ── bash, async, in its own process group ──────────────────────────────────────────────────────────────────────
class BashResult:
    def __init__(self, command: str, code: int | None, stdout: str, stderr: str, timed_out: bool, seconds: float):
        self.command, self.code, self.stdout, self.stderr = command, code, stdout, stderr
        self.timed_out, self.seconds = timed_out, seconds

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out

    def __str__(self) -> str:
        return self.stdout + (("\n" if self.stdout and not self.stdout.endswith("\n") else "") + self.stderr
                              if self.stderr else "")

    def __repr__(self) -> str:
        head = f"exit {self.code}" + (" (timed out)" if self.timed_out else "") + f", {self.seconds:.1f}s"
        return f"<BashResult {head}>\n{_summary(str(self), 8000)}"


def _tail(data: bytes) -> str:
    if len(data) > CAPTURE_CAP:
        data = b"[... earlier output dropped ...]\n" + data[-CAPTURE_CAP:]
    return data.decode("utf-8", "replace")


def _kill_group(proc, sig) -> None:
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


async def _bash(command: str, timeout: float | None, cwd: str | None, env: dict | None) -> BashResult:
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        "/bin/bash", "-c", command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, cwd=cwd or os.getcwd(), env={**os.environ, **(env or {})},
        start_new_session=True)
    timed_out = False
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        timed_out = True
        _kill_group(proc, signal.SIGTERM)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), 3)
        except asyncio.TimeoutError:
            _kill_group(proc, signal.SIGKILL)
            out, err = await proc.communicate()
    except asyncio.CancelledError:
        _kill_group(proc, signal.SIGTERM)
        await asyncio.sleep(0.2)
        _kill_group(proc, signal.SIGKILL)
        raise
    return BashResult(command, proc.returncode, _tail(out or b""), _tail(err or b""), timed_out,
                      time.monotonic() - t0)


def bash(command: str, *, timeout: float | None = 300, cwd: str | None = None, env: dict | None = None,
         background: bool = False):
    """`await bash("cmd")` → BashResult (stdout, stderr, code, ok). background=True → a Job right away (an engine
    job: the agent is woken when it ends). Runs in this kernel's sandbox (no root, no secrets, workspace only)."""
    if background:
        return spawn(_bash(command, timeout, cwd, env), label=f"bash: {command[:120]}")
    return _bash(command, timeout, cwd, env)


# ── delegation: the engine's own sub-agents (Walter Router picks their model) ─────────────────────────────────
_SUBAGENT_PARAMS: set | None = None


async def _subagent_params() -> set:
    global _SUBAGENT_PARAMS
    if _SUBAGENT_PARAMS is None:
        try:
            schema = await tools.describe("subagent")
            _SUBAGENT_PARAMS = set(((schema or {}).get("parameters") or {}).get("properties") or {})
        except Exception:  # noqa: BLE001 — the call itself will report a missing tool
            _SUBAGENT_PARAMS = set()
    return _SUBAGENT_PARAMS


async def delegate(prompt: str, *, description: str | None = None, poste: str | None = None,
                   effort: str | None = None, background: bool = False) -> Any:
    """A sub-agent of the engine on a self-contained task; waits for and returns its result. `poste` = a Walter
    Router task (`code`, `general`, `document`…) for the child's model; omitted = the engine's default (the Router's
    plan). `background=True` returns the sub-agent's id at once; the engine wakes the session when it settles."""
    args: dict[str, Any] = {"description": (description or " ".join(prompt.split()[:6]))[:80], "prompt": prompt}
    if poste:
        args.update(provider="walter", model=poste)
    if effort:
        args["reasoning_effort"] = effort
    if "run_in_background" in await _subagent_params():
        args["run_in_background"] = bool(background)
    return await tools.call("subagent", **args)


async def delegate_all(tasks: list, *, limit: int = 4) -> list:
    """Several sub-agents in parallel (at most `limit` at once): each item a prompt or a dict of delegate()'s
    arguments. Returns the results in order; a failed one is its exception."""
    sem = asyncio.Semaphore(max(1, int(limit)))

    async def one(item):
        async with sem:
            return await (delegate(item) if isinstance(item, str) else delegate(**item))
    return await asyncio.gather(*(one(t) for t in tasks), return_exceptions=True)


tools = Tools()


# ── cells ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _compile(code: str, filename: str) -> tuple[list[types.CodeType], bool]:
    linecache.cache[filename] = (len(code), None, code.splitlines(keepends=True), filename)
    tree = ast.parse(code, filename)
    trailing = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        trailing = ast.Expression(tree.body.pop().value)
    flags = ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
    codes = []
    if tree.body:
        codes.append(compile(tree, filename, "exec", flags=flags, dont_inherit=True))
    if trailing is not None:
        codes.append(compile(trailing, filename, "eval", flags=flags, dont_inherit=True))
    return codes, trailing is not None


def _error(exc: BaseException, filename: str) -> dict:
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename.startswith("<cell")]
    lines = traceback.format_list(frames[-8:]) + traceback.format_exception_only(type(exc), exc)
    text = "".join(lines)
    return {"type": type(exc).__name__, "message": _summary(str(exc), 2000),
            "traceback": text[-6000:]}


def user_names() -> list[dict]:
    out = []
    for name, value in NS.items():
        if name.startswith("_") or name in INJECTED:
            continue
        kind = "module" if isinstance(value, types.ModuleType) else type(value).__name__
        out.append({"name": name, "type": kind})
    return out[:200]


async def _run_cell(req: dict) -> None:
    global _cell_id
    cid = str(req.get("id"))
    if isinstance(req.get("tools"), list):
        tools._names = [str(n) for n in req["tools"]]
    filename = f"<cell {next(_cells)}>"
    CELL.set(cid)
    before = set(NS)
    status, err = "ok", None
    try:
        codes, has_tail = _compile(str(req.get("code") or ""), filename)
        value = None
        for code in codes:
            value = eval(code, NS)  # noqa: S307 — running the model's cell is this kernel's job
            if code.co_flags & inspect.CO_COROUTINE:
                value = await value
        if has_tail and value is not None:
            NS["_"] = value
            send({"event": "result", "id": cid, "text": _summary(value, RESULT_CAP, as_repr=True)})
    except (asyncio.CancelledError, KeyboardInterrupt):
        status, err = "interrupted", {"type": "KeyboardInterrupt", "message": "interrupted"}
    except BaseException as exc:  # noqa: BLE001 — every failure of a cell is reported, the kernel keeps serving
        status, err = "error", _error(exc, filename)
    done = {"event": "done", "id": cid, "status": status}
    if err:
        done["error"] = err
    if set(NS) != before:
        done["names"] = user_names()
    running = [{"job": j.key, "engine": j.engine_id, "label": j.label} for j in _jobs.values() if not j.done()]
    if running:
        done["jobs"] = running
    send(done)


# ── snapshots ──────────────────────────────────────────────────────────────────────────────────────────────────
def snapshot(path: str = SNAPSHOT) -> dict:
    import dill
    records: dict[str, tuple[str, Any]] = {}
    skipped: dict[str, str] = {}
    total = 0
    for name, value in list(NS.items()):
        if name.startswith("_") or name in INJECTED:
            continue
        if isinstance(value, types.ModuleType):
            records[name] = ("module", value.__name__)
            continue
        if isinstance(value, (Job, asyncio.Task, asyncio.Future)) or inspect.iscoroutine(value):
            skipped[name] = "live task"
            continue
        try:
            blob = dill.dumps(value, recurse=True)
        except Exception as exc:  # noqa: BLE001 — sockets, open files, processes… stay out
            skipped[name] = type(exc).__name__
            continue
        if len(blob) > MAX_VAR_BYTES:
            skipped[name] = "too large"
            continue
        if total + len(blob) > MAX_TOTAL_BYTES:
            skipped[name] = "snapshot full"
            continue
        total += len(blob)
        records[name] = ("value", blob)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        pickle.dump({"version": 1, "at": time.time(), "records": records}, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)
    return {"saved": len(records), "bytes": total, "skipped": skipped}


def _rebind(fn: types.FunctionType) -> types.FunctionType:
    """dill restores a cell's function with a private copy of its globals: give it the live namespace back."""
    new = types.FunctionType(fn.__code__, NS, fn.__name__, fn.__defaults__, fn.__closure__)
    new.__kwdefaults__, new.__qualname__ = fn.__kwdefaults__, fn.__qualname__
    new.__dict__.update(fn.__dict__)
    new.__annotations__ = getattr(fn, "__annotations__", {})
    new.__module__ = "__main__"
    return new


def restore(path: str = SNAPSHOT) -> dict:
    if not os.path.exists(path):
        return {"restored": 0, "missing": True}
    import dill
    with open(path, "rb") as fh:
        data = pickle.load(fh)  # noqa: S301 — written by this kernel, in its own workspace
    restored, failed = [], {}
    for name, (kind, payload) in data.get("records", {}).items():
        try:
            NS[name] = importlib.import_module(payload) if kind == "module" else dill.loads(payload)
            restored.append(name)
        except Exception as exc:  # noqa: BLE001
            failed[name] = f"{type(exc).__name__}: {exc}"[:200]
    for name in restored:
        value = NS[name]
        if isinstance(value, types.FunctionType) and value.__globals__ is not NS:
            NS[name] = _rebind(value)
        elif isinstance(value, type) and value.__module__ == "__main__":
            for attr, member in list(vars(value).items()):
                if isinstance(member, types.FunctionType) and member.__globals__ is not NS:
                    setattr(value, attr, _rebind(member))
    return {"restored": len(restored), "failed": failed, "at": data.get("at")}


# ── serving ────────────────────────────────────────────────────────────────────────────────────────────────────
def _on_sigint(signum, frame) -> None:
    """KeyboardInterrupt only inside the running cell's own code (synchronous work the cancel could not reach)."""
    task = asyncio.current_task(_loop) if _loop and _loop.is_running() else None
    if task is not None and task is _cell_task:
        raise KeyboardInterrupt


def _interrupt() -> None:
    cell = _cell_task
    if cell is None or cell.done():
        return
    _loop.call_soon_threadsafe(cell.cancel)

    def harder():
        time.sleep(1.0)
        if _cell_task is cell and not cell.done():
            import _thread
            _thread.interrupt_main()
    threading.Thread(target=harder, daemon=True).start()


def _reader(fd: int) -> None:
    with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except ValueError:
                send({"event": "error", "message": "protocol: not JSON"})
                continue
            kind = req.get("type")
            if kind == "interrupt":
                _interrupt()
            elif kind == "host_reply":
                fut = _pending.get(str(req.get("id")))
                if fut is not None:
                    _loop.call_soon_threadsafe(lambda f=fut, r=req: f.done() or f.set_result(r))
            elif kind == "job_kill":
                job = _jobs.get(str(req.get("job")))
                if job is not None:
                    _loop.call_soon_threadsafe(job.kill)
            elif kind == "job_bound":
                job = _jobs.get(str(req.get("job")))
                if job is not None:
                    if req.get("engine"):
                        job.engine_id = str(req["engine"])
                    elif req.get("error"):       # the engine refused it (job limit…): it does not run unseen
                        job.refused = str(req["error"])[:500]
                    job.bound.set()
            else:
                _loop.call_soon_threadsafe(_queue.put_nowait, req)
    _loop.call_soon_threadsafe(_queue.put_nowait, {"type": "shutdown", "reason": "eof"})


async def _serve() -> None:
    global _cell_task, _cell_id, _stopping
    while True:
        req = await _queue.get()
        kind = req.get("type")
        rid = req.get("id")
        if kind == "execute":
            _cell_id = str(rid)
            _cell_task = _loop.create_task(_run_cell(req), context=contextvars.copy_context())
            try:
                await asyncio.shield(_cell_task)
            except BaseException:  # noqa: BLE001 — the cell reports its own outcome
                pass
            _cell_task, _cell_id = None, None
        elif kind == "snapshot":
            try:
                send({"event": "done", "id": rid, "status": "ok", "snapshot": snapshot()})
            except Exception as exc:  # noqa: BLE001
                send({"event": "done", "id": rid, "status": "error", "error": {"type": type(exc).__name__,
                                                                              "message": str(exc)[:500]}})
        elif kind == "restore":
            try:
                send({"event": "done", "id": rid, "status": "ok", "restore": restore(), "names": user_names()})
            except Exception as exc:  # noqa: BLE001
                send({"event": "done", "id": rid, "status": "error", "error": {"type": type(exc).__name__,
                                                                              "message": str(exc)[:500]}})
        elif kind == "names":
            send({"event": "done", "id": rid, "status": "ok", "names": user_names(),
                  "jobs": [{"job": j.key, "engine": j.engine_id, "label": j.label, "running": not j.done()}
                           for j in _jobs.values()]})
        elif kind == "shutdown":
            _stopping = True
            for job in _jobs.values():
                job.kill()
            if req.get("snapshot", True):
                try:
                    snapshot()
                except Exception:  # noqa: BLE001 — leaving anyway; the previous snapshot stays
                    pass
            send({"event": "bye", "id": rid})
            _loop.stop()
            return
        else:
            send({"event": "done", "id": rid, "status": "error",
                  "error": {"type": "ProtocolError", "message": f"unknown request {kind!r}"}})


def _on_sigterm(signum, frame) -> None:
    if _loop is not None:
        _loop.call_soon_threadsafe(_queue.put_nowait, {"type": "shutdown", "reason": "sigterm"})


def setup_namespace() -> dict:
    """The cells' namespace: a fresh `__main__` module (dill then pickles cell-defined functions by value)."""
    global NS
    import builtins
    module = types.ModuleType("__main__")
    sys.modules["__main__"] = module
    NS = module.__dict__
    helpers = {"tools": tools, "bash": bash, "spawn": spawn, "jobs": jobs, "delegate": delegate,
               "delegate_all": delegate_all, "ToolError": ToolError, "asyncio": asyncio}
    NS.update(helpers)
    NS["__builtins__"] = builtins
    INJECTED.update(helpers)
    INJECTED.update({"__name__", "__doc__", "__package__", "__loader__", "__spec__", "__builtins__"})
    return NS


def main() -> None:
    global _proto, _loop, _queue
    proto_fd = os.dup(1)
    _proto = os.fdopen(proto_fd, "w", encoding="utf-8", buffering=1)
    in_fd = os.dup(0)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    for fd, stream in ((1, "stdout"), (2, "stderr")):
        r, w = os.pipe()
        os.dup2(w, fd)
        os.close(w)
        threading.Thread(target=_pump, args=(r, stream), daemon=True).start()
    sys.stdout, sys.stderr = _Writer("stdout"), _Writer("stderr")
    sys.stdin = open(os.devnull)  # noqa: SIM115

    setup_namespace()

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _queue = asyncio.Queue()
    signal.signal(signal.SIGINT, _on_sigint)
    signal.signal(signal.SIGTERM, _on_sigterm)
    threading.Thread(target=_reader, args=(in_fd,), daemon=True).start()
    send({"event": "ready", "protocol": PROTOCOL, "python": sys.version.split()[0], "pid": os.getpid()})
    _loop.create_task(_serve())
    while True:
        try:
            _loop.run_forever()
            break
        except KeyboardInterrupt:   # landed outside the cell's code: the cancel already did the work
            continue
    os._exit(0)


if __name__ == "__main__":
    main()
