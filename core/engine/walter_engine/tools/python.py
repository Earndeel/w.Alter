"""Walter Engine — the persistent Python kernel as the engine's programmable centre (2026-11-17).

One kernel per conversation (and per sub-agent), started on first use, kept across turns, compactions and engine
restarts (its namespace is snapshotted after each cell and restored when it comes back). It runs with the ENGINE's
rights (`[native] python = "full"`, Monsieur 2026-11-17: the main Python environment is no longer shut in a bubble):
real Walter directories, local services, system commands, package installs, databases — the same reach as `bash`.
What a call may do is decided where every other call is decided: Walter's policy on the tools it calls
(`await tools.<name>(...)` goes through the engine's one `execute`, with the same never-list, door preset, disclosure
check, approvals and journal as a direct call), and the never-list on its own text (a cell is judged like a shell
command). `python = "sandbox"` keeps the former bubble (systemd transient unit as `walter-sandbox`) for whoever wants
it; isolated environments for third-party programs stay available inside the kernel (venvs, `bash()` in a unit).

Protocol walter-1 (core/engine/plugins/python/runtime/walter_kernel.py): the kernel asks the host for tools
(`host` events), declares background work (`job` events: the engine's durable job registry, which wakes the session
when it settles), streams output; the host executes cells one at a time per kernel and snapshots after each.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from . import Exec, Result, Tool, clip, obj
from .. import config

log = logging.getLogger("walter_engine.python")

DENIED_NETWORKS = ["127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
                   "100.64.0.0/10", "fc00::/7", "fe80::/10"]

DESCRIPTION = (
    "Run Python in your persistent kernel (one per conversation): variables, imports and functions persist across "
    "calls, turns, compactions and engine restarts. Top-level `await` works; the last expression's repr is returned, "
    "print() output is shown. Keep large data in variables instead of printing it. The kernel runs with the engine's "
    "rights: Walter's real directories, local services and databases, system commands (`await bash(\"cmd\")` → "
    ".stdout .stderr .code .ok), `pip install`. Every engine tool is reachable: `await tools.search(\"mémoire\")` finds "
    "them, `await tools.describe(name)` gives their parameters, `await tools.<name>(**args)` runs one under the same "
    "policy as a direct call (Walter tools by their short name too, e.g. `await tools.memory_search(query=…)`); run "
    "independent calls together with `await asyncio.gather(...)`. Long work: `bash(\"cmd\", background=True)` or "
    "`spawn(coro, label)` start an engine job and return it at once (job.id for job_output / job_kill) — end your turn, "
    "you are woken when it ends. `await delegate(prompt, poste=\"code\")` runs a sub-agent in its own context and "
    "returns its result; `await delegate_all([...])` runs several at once.")


class Kernel:
    def __init__(self, host: "PythonHost", agent):
        self.host = host
        self.agent = agent
        self.key = hashlib.sha256(agent.sid.encode()).hexdigest()[:16]
        self.dir = host.root / self.key
        self.snapshot_path = self.dir / ".snapshot" / "state.pkl"
        self.proc: asyncio.subprocess.Process | None = None
        self.waiters: dict[str, asyncio.Future] = {}
        self.cells: dict[str, dict] = {}
        self.jobs: dict[str, str] = {}          # kernel job key → engine job id
        self.ids = 0
        self.lane = asyncio.Lock()
        self.stderr = ""
        self.restored: dict | None = None
        self.idle: asyncio.TimerHandle | None = None
        self.names: list[str] = []
        self.started_ms: int | None = None

    def log(self, event: str, **extra) -> None:
        try:
            day = time.strftime("%Y-%m-%d", time.gmtime())
            with open(self.host.root / f"kernels-{day}.jsonl", "a") as fh:
                fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "key": self.key,
                                     "session": self.agent.sid, "event": event, **extra}) + "\n")
        except OSError:
            pass

    def argv_env(self) -> tuple[list[str], dict, str]:
        s = self.host.s
        py = s.python_interpreter
        if s.python != "sandbox":
            env = {**os.environ, "PYTHONPATH": str(config.KERNEL_RUNTIME_DIR), "PYTHONUNBUFFERED": "1",
                   "MPLBACKEND": "Agg", "WALTER_KERNEL_SNAPSHOT": str(self.snapshot_path), "WALTER_KERNEL_BIND_JOBS": "1",
                   "WALTER_SESSION_ID": self.agent.key, "PATH": f"{Path(py).parent}:{os.environ.get('PATH', '/usr/bin:/bin')}"}
            for k in ("WALTER_LLM_TOKEN", "WALTER_MEMORY_GATEWAY_TOKEN", "WALTER_ENGINE_API_TOKEN"):
                env.pop(k, None)
            return [py, "-P", "-c", "import walter_kernel; walter_kernel.main()"], env, self.agent.cwd
        unit = f"walter-python-{self.key}"
        props = ["User=walter-sandbox", "Group=walter-sandbox", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes",
                 "PrivateDevices=yes", "NoNewPrivileges=yes", "CapabilityBoundingSet=", "AmbientCapabilities=",
                 "RestrictSUIDSGID=yes", "ProtectKernelTunables=yes", "ProtectKernelModules=yes", "ProtectKernelLogs=yes",
                 "ProtectControlGroups=yes", "UMask=0077", f"BindPaths={self.dir}:/kernel",
                 f"IPAddressDeny={' '.join(DENIED_NETWORKS)}", "IPAddressAllow=127.0.0.53/32", "MemoryMax=4G",
                 "TasksMax=256", "CPUQuota=200%", "KillMode=control-group"]
        senv = {"HOME": "/kernel", "PATH": f"{Path(py).parent}:/usr/local/bin:/usr/bin:/bin",
                "PYTHONPATH": str(config.KERNEL_RUNTIME_DIR), "PYTHONUNBUFFERED": "1", "LANG": "C.UTF-8",
                "WALTER_KERNEL_SNAPSHOT": "/kernel/.snapshot/state.pkl", "WALTER_KERNEL_BIND_JOBS": "1"}
        argv = ["systemd-run", "--wait", "--pipe", "--collect", "--quiet", f"--unit={unit}", "--working-directory=/kernel",
                *[f"--property={p}" for p in props], *[f"--setenv={k}={v}" for k, v in senv.items()],
                py, "-P", "-c", "import walter_kernel; walter_kernel.main()"]
        return argv, {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}, "/"

    async def start(self) -> None:
        t0 = time.monotonic()
        (self.dir / ".snapshot").mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.host.s.python == "sandbox":
            import pwd
            pw = pwd.getpwnam("walter-sandbox")
            for p in (self.dir, self.dir / ".snapshot"):
                os.chown(p, pw.pw_uid, pw.pw_gid)
        restore = self.snapshot_path.exists()
        argv, env, cwd = self.argv_env()
        self.proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                         stderr=asyncio.subprocess.PIPE, env=env, cwd=cwd, limit=64 * 2**20)
        loop = asyncio.get_running_loop()
        ready = loop.create_future()
        self.waiters["ready"] = ready
        loop.create_task(self._read(self.proc))
        loop.create_task(self._drain(self.proc))
        await asyncio.wait_for(ready, 30)
        if restore:
            try:
                r = await self.request({"type": "restore"}, 120)
                self.restored = r.get("restore") if r.get("status") == "ok" else {"failed": r.get("error")}
                self.names = r.get("names") or self.names
            except Exception as e:  # noqa: BLE001
                self.restored = {"failed": {"snapshot": str(e)[:200]}}
        self.started_ms = int((time.monotonic() - t0) * 1000)
        self.log("start", ms=self.started_ms, restored=(self.restored or {}).get("restored", 0), mode=self.host.s.python)
        self.touch()

    def touch(self) -> None:
        if self.idle:
            self.idle.cancel()
        self.idle = asyncio.get_running_loop().call_later(self.host.s.python_idle_s, self._idle_stop)

    def _idle_stop(self) -> None:
        if self.cells or self.jobs:
            return self.touch()
        self.log("idle_stop")
        asyncio.get_running_loop().create_task(self.stop("idle"))

    async def _read(self, proc) -> None:
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                self.on_event(ev)
        finally:
            why = RuntimeError(f"python kernel exited ({proc.returncode}){': ' + self.stderr[-300:] if self.stderr else ''}")
            for fut in self.waiters.values():
                if not fut.done():
                    fut.set_exception(why)
            self.waiters.clear()
            for key, jid in list(self.jobs.items()):
                self.host.engine.jobs.settle_external(jid, "failed", "the python kernel stopped; background work does not survive it")
            self.jobs.clear()
            if self.idle:
                self.idle.cancel()
            if self.host.kernels.get(self.agent.sid) is self:
                del self.host.kernels[self.agent.sid]
            self.log("exit", code=proc.returncode)

    async def _drain(self, proc) -> None:
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            self.stderr = (self.stderr + line.decode("utf-8", "replace"))[-4000:]

    def send(self, obj_: dict) -> None:
        if not self.proc or self.proc.returncode is not None or not self.proc.stdin:
            raise RuntimeError("python kernel is not running")
        self.proc.stdin.write((json.dumps(obj_) + "\n").encode())

    async def request(self, req: dict, timeout: float | None = None) -> dict:
        self.ids += 1
        rid = req.get("id") or f"r{self.ids}"
        fut = asyncio.get_running_loop().create_future()
        self.waiters[rid] = fut
        try:
            self.send({**req, "id": rid})
            return await (asyncio.wait_for(fut, timeout) if timeout else fut)
        finally:
            self.waiters.pop(rid, None)

    def on_event(self, ev: dict) -> None:
        kind = ev.get("event")
        if kind == "ready":
            f = self.waiters.pop("ready", None)
            if f and not f.done():
                f.set_result(ev)
        elif kind == "done":
            f = self.waiters.get(ev.get("id"))
            if f and not f.done():
                f.set_result(ev)
        elif kind == "out":
            cell = self.cells.get(ev.get("id")) if ev.get("id") else None
            if cell is not None:
                cell["out"].append(ev.get("text") or "")
            elif ev.get("job") and ev["job"] in self.jobs:
                self.host.engine.jobs.append(self.jobs[ev["job"]], ev.get("text") or "")
        elif kind == "result":
            cell = self.cells.get(ev.get("id"))
            if cell is not None:
                cell["result"] = ev.get("text")
        elif kind == "host":
            asyncio.get_running_loop().create_task(self.on_host(ev))
        elif kind == "host_cancel":
            t = self.host.host_tasks.pop(ev.get("id"), None)
            if t:
                t.cancel()
        elif kind == "job":
            self.on_job(ev)

    async def on_host(self, ev: dict) -> None:
        hid = ev.get("id")
        cell = self.cells.get(ev.get("cell")) if ev.get("cell") else None
        self.host.host_tasks[hid] = asyncio.current_task()
        try:
            method, params = ev.get("method"), ev.get("params") or {}
            reg = self.host.engine.registry
            if method == "search":
                result = reg.search(params.get("query"), params.get("limit") or 8)
            elif method == "describe":
                result = reg.describe(_resolve(reg, str(params.get("name") or "")))
            elif method == "tool":
                name = _resolve(reg, str(params.get("name") or ""))
                if name == "python":
                    raise RuntimeError("python cannot call itself")
                args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
                cancel = cell["exec"].cancel if cell else asyncio.Event()
                res = await self.host.engine.execute_tool(
                    self.agent, name, args, via="python", cancel=cancel,
                    parent_call=cell["exec"].call_id if cell else f"python:{self.key}:{ev.get('job') or 'job'}",
                    turn=cell["exec"].turn if cell else None, step=cell["exec"].step if cell else None)
                if res.is_error:
                    raise RuntimeError(res.content[:4000] or f"{name} failed")
                result = res.value if res.value is not None else res.content
            else:
                raise RuntimeError(f"unknown host method {method}")
            self.send({"type": "host_reply", "id": hid, "ok": True, "result": _jsonable(result)})
        except asyncio.CancelledError:
            try:
                self.send({"type": "host_reply", "id": hid, "ok": False, "error": "cancelled"})
            except RuntimeError:
                pass
        except Exception as e:  # noqa: BLE001
            try:
                self.send({"type": "host_reply", "id": hid, "ok": False, "error": str(e)[:4000]})
            except RuntimeError:
                pass
        finally:
            self.host.host_tasks.pop(hid, None)

    def on_job(self, ev: dict) -> None:
        key, state = ev.get("job"), ev.get("state")
        jobs = self.host.engine.jobs
        if state == "start":
            def cancel(k=key):
                try:
                    self.send({"type": "job_kill", "job": k})
                except RuntimeError:
                    pass
            j = jobs.register_external(kind="python", label=f"python: {ev.get('label') or ''}", owner=self.agent.sid,
                                       cancel=cancel)
            self.jobs[key] = j.id
            try:
                self.send({"type": "job_bound", "job": key, "engine": j.id})
            except RuntimeError:
                pass
            return
        jid = self.jobs.pop(key, None)
        if not jid:
            return
        status = {"completed": "completed", "killed": "killed"}.get(state, "failed")
        jobs.settle_external(jid, status, str(ev.get("result") or "")[:4000] or None)
        self.touch()

    async def cell(self, code: str, ex: Exec, timeout_s: float) -> str:
        async with self.lane:
            self.ids += 1
            cid = f"c{self.ids}"
            cell = {"exec": ex, "out": [], "result": None, "timed_out": False}
            self.cells[cid] = cell
            names = sorted({n.removeprefix("mcp__walter__") for n in self.host.engine.registry.names() if n != "python"})
            t0 = time.monotonic()
            killed = False

            async def interrupt():
                nonlocal killed
                try:
                    self.send({"type": "interrupt"})
                except RuntimeError:
                    return
                await asyncio.sleep(5)
                if cid in self.cells:
                    killed = True
                    await self.kill("interrupt not honoured")

            watcher = asyncio.ensure_future(ex.cancel.wait())
            req = asyncio.ensure_future(self.request({"type": "execute", "id": cid, "code": code, "tools": names}))
            intr = None
            try:
                done, _ = await asyncio.wait({req, watcher}, timeout=timeout_s, return_when=asyncio.FIRST_COMPLETED)
                if req not in done:
                    cell["timed_out"] = watcher not in done
                    intr = asyncio.ensure_future(interrupt())
                    try:
                        await asyncio.wait_for(asyncio.shield(req), 15)
                    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                        pass
                try:
                    res = req.result() if req.done() else {"status": "interrupted"}
                except Exception as e:  # noqa: BLE001
                    res = {"status": "interrupted" if killed else "error",
                           "error": {"type": "KernelExited", "message": f"{str(e)[:300]} — the next call restarts it from the last snapshot"}}
            finally:
                watcher.cancel()
                if intr:
                    intr.cancel()
                self.cells.pop(cid, None)
            if res.get("names"):
                self.names = res["names"]
            self.log("cell", ms=int((time.monotonic() - t0) * 1000), status=res.get("status"), timed_out=cell["timed_out"] or None)
            if self.proc and self.proc.returncode is None:
                try:
                    await asyncio.wait_for(self.request({"type": "snapshot"}), 60)
                except Exception:  # noqa: BLE001 — the previous snapshot stays
                    pass
            self.touch()
            return self.render(cell, res, timeout_s)

    def render(self, cell: dict, done: dict, timeout_s: float) -> str:
        parts = []
        out = "".join(cell["out"])
        if out:
            parts.append(out.rstrip("\n"))
        if cell["result"] is not None:
            parts.append(f"→ {cell['result']}")
        err = done.get("error") or {}
        if done.get("status") == "error":
            parts.append(str(err.get("traceback") or f"{err.get('type')}: {err.get('message')}").rstrip("\n"))
        if done.get("status") == "interrupted":
            parts.append(f"[interrupted: the cell exceeded {int(timeout_s)} s — use background=True / spawn() for long work]"
                         if cell["timed_out"] else f"[interrupted]{' ' + err['message'] if err.get('type') == 'KernelExited' else ''}")
        if done.get("jobs"):
            parts.append("[background: " + "; ".join(f"{j.get('engine') or j.get('job')} {j.get('label')}" for j in done["jobs"])
                         + " — you will be woken when they end; job_output / job_kill take these ids]")
        if self.restored and not self.restored.get("reported"):
            self.restored["reported"] = True
            failed = list((self.restored.get("failed") or {}).keys())
            parts.insert(0, f"[kernel restarted: {self.restored.get('restored', 0)} variables restored from the last snapshot"
                            + (f", not restored: {', '.join(failed[:10])}" if failed else "") + "]")
        return clip("\n".join(parts) or "(no output)", 20_000)

    async def stop(self, reason: str) -> None:
        if not self.proc or self.proc.returncode is not None:
            return
        try:
            self.send({"type": "shutdown", "reason": reason})
            await asyncio.wait_for(self.proc.wait(), 20)
        except (RuntimeError, asyncio.TimeoutError):
            await self.kill(f"{reason}: no clean exit")

    async def kill(self, reason: str) -> None:
        self.log("kill", reason=reason)
        if self.host.s.python == "sandbox":
            p = await asyncio.create_subprocess_exec("systemctl", "kill", "--signal=SIGKILL", f"walter-python-{self.key}.service")
            await p.wait()
        try:
            self.proc.kill()
        except (ProcessLookupError, AttributeError):
            pass


def _resolve(reg, name: str) -> str:
    if name in reg.tools:
        return name
    if "mcp__walter__" + name in reg.tools:
        return "mcp__walter__" + name
    return name


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return json.loads(json.dumps(v, default=str))


class PythonHost:
    def __init__(self, engine, settings: config.Settings):
        self.engine = engine
        self.s = settings
        self.root = settings.python_dir
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.kernels: dict[str, Kernel] = {}
        self.starting: dict[str, asyncio.Future] = {}
        self.host_tasks: dict[str, asyncio.Task] = {}

    async def kernel(self, agent) -> Kernel:
        k = self.kernels.get(agent.sid)
        if k and k.proc and k.proc.returncode is None:
            k.agent = agent
            return k
        if agent.sid in self.starting:
            return await self.starting[agent.sid]
        fut = asyncio.get_running_loop().create_future()
        self.starting[agent.sid] = fut
        try:
            k = Kernel(self, agent)
            await k.start()
            self.kernels[agent.sid] = k
            fut.set_result(k)
            return k
        except Exception as e:
            fut.set_exception(e)
            fut.exception()
            raise
        finally:
            self.starting.pop(agent.sid, None)

    async def run(self, args: dict, ex: Exec) -> Result:
        code = str(args.get("code") or "")
        if not code.strip():
            return Result("code must be non-empty", True)
        timeout = float(args.get("timeout_s") or 600)
        timeout = max(1.0, min(timeout, 6 * 3600.0))
        k = await self.kernel(ex.agent)
        text = await k.cell(code, ex, timeout)
        failed = text.startswith("Traceback") or "\n[interrupted" in text or text.startswith("[interrupted")
        return Result(text, failed, value=text)

    async def stop_all(self, reason: str) -> None:
        await asyncio.gather(*(k.stop(reason) for k in list(self.kernels.values())), return_exceptions=True)

    def tool(self) -> Tool:
        return Tool("python", DESCRIPTION, obj({
            "code": {"type": "string", "description": "Python code to run in the persistent kernel."},
            "description": {"type": "string", "description": "A short label for what this code does (shown to Monsieur)."},
            "timeout_s": {"type": "number", "description": "Seconds before the cell is interrupted (default 600)."}},
            ["code"]), self.run)
