"""Walter Engine — durable background jobs (2026-11-17).

Work that outlives a model step: a shell command in the background, a Python `spawn()`, a sub-agent run in the
background. Each job belongs to a session; its output goes to a 0600 log file (readable after a restart with
`job_output`), its state to `jobs.json`. When a job settles, the engine is told (`on_settled`): the owning session gets
a notice and is woken if idle. A job still running when the engine stops is never silently lost nor silently re-run:
at the next start it is marked `lost` and its session is told (with the idempotency contract the job declared —
`idempotent` jobs may be started again by the agent without checking, the others must be checked first).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

TAIL = 16_000


@dataclass
class Job:
    id: str
    kind: str                     # bash | python | subagent
    label: str
    owner: str                    # session id
    status: str = "running"       # running | completed | failed | killed | lost
    started: float = field(default_factory=time.time)
    ended: float | None = None
    code: int | None = None
    result: str | None = None
    idempotent: bool = False
    wake: bool = True
    meta: dict = field(default_factory=dict)

    def view(self) -> dict:
        d = asdict(self)
        d["runtime_s"] = round((self.ended or time.time()) - self.started, 1)
        return d


class Jobs:
    def __init__(self, root: Path, on_settled: Callable[[Job], None] | None = None):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = root / "jobs.json"
        self.jobs: dict[str, Job] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancels: dict[str, Callable[[], Any]] = {}
        self.on_settled = on_settled
        self.stopping = False
        self._load()

    # ── persistence ──
    def _load(self) -> None:
        try:
            rows = json.loads(self.file.read_text())
        except (OSError, ValueError):
            rows = []
        for r in rows:
            try:
                self.jobs[r["id"]] = Job(**{k: r[k] for k in Job.__dataclass_fields__ if k in r})
            except (KeyError, TypeError):
                continue

    def _save(self) -> None:
        cutoff = time.time() - 7 * 86400
        rows = [asdict(j) for j in self.jobs.values() if j.status == "running" or (j.ended or 0) > cutoff]
        tmp = self.file.with_suffix(f".{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(rows, fh)
        os.replace(tmp, self.file)

    def recover(self) -> list[Job]:
        """Jobs a previous engine process left running: marked lost (never re-run by the engine itself)."""
        lost = []
        for j in self.jobs.values():
            if j.status == "running" and j.id not in self.tasks:
                j.status, j.ended = "lost", time.time()
                j.result = "le moteur a redémarré pendant ce travail ; son effet réel est à vérifier avant de le relancer"
                lost.append(j)
        if lost:
            self._save()
        return lost

    def log_path(self, jid: str) -> Path:
        return self.root / f"{jid}.log"

    def append(self, jid: str, text: str) -> None:
        if not text:
            return
        p = self.log_path(jid)
        new = not p.exists()
        with open(p, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(text)
        if new:
            os.chmod(p, 0o600)

    def output(self, jid: str, offset: int = 0, limit: int = TAIL) -> dict:
        j = self.jobs.get(jid)
        if not j:
            raise KeyError(jid)
        try:
            data = self.log_path(jid).read_text(errors="replace")
        except OSError:
            data = ""
        total = len(data)
        if offset < 0:
            offset = max(0, total + offset)
        chunk = data[offset: offset + limit] if offset else data[-limit:]
        start = offset if offset else max(0, total - limit)
        return {"job": j.view(), "output": chunk, "offset": start, "chars": total,
                "truncated_before": start > 0, "next_offset": start + len(chunk) if start + len(chunk) < total else None}

    # ── lifecycle ──
    def start(self, *, kind: str, label: str, owner: str, work: Callable[["Job"], Awaitable[Any]],
              cancel: Callable[[], Any] | None = None, idempotent: bool = False, wake: bool = True,
              meta: dict | None = None) -> Job:
        jid = f"job-{uuid.uuid4().hex[:10]}"
        j = Job(id=jid, kind=kind, label=label[:200], owner=owner, idempotent=idempotent, wake=wake, meta=meta or {})
        self.jobs[jid] = j
        if cancel:
            self.cancels[jid] = cancel
        self._save()

        async def runner():
            try:
                res = await work(j)
                if j.status == "running":
                    j.status = "completed"
                    if isinstance(res, dict):
                        j.code = res.get("code", j.code)
                        if res.get("code") not in (None, 0):
                            j.status = "failed"
                        j.result = str(res.get("result") or "")[:4000] or None
                    elif res is not None:
                        j.result = str(res)[:4000]
            except asyncio.CancelledError:
                if self.stopping:          # the engine stops: the job stays `running` on disk, reported lost next start
                    self.tasks.pop(jid, None)
                    return
                j.status = "killed"
            except Exception as e:  # noqa: BLE001
                j.status = "failed"
                j.result = f"{type(e).__name__}: {str(e)[:500]}"
            finally:
                j.ended = time.time()
                self.tasks.pop(jid, None)
                self.cancels.pop(jid, None)
                self._save()
                if self.on_settled:
                    try:
                        self.on_settled(j)
                    except Exception:  # noqa: BLE001
                        pass

        self.tasks[jid] = asyncio.get_running_loop().create_task(runner(), name=f"job:{jid}")
        return j

    def settle_external(self, jid: str, status: str, result: str | None = None, code: int | None = None) -> None:
        """A job driven from outside a task here (a Python kernel's spawn): its end, reported by its owner."""
        j = self.jobs.get(jid)
        if not j or j.status != "running":
            return
        j.status, j.result, j.code, j.ended = status, (result or None), code, time.time()
        self.tasks.pop(jid, None)
        self.cancels.pop(jid, None)
        self._save()
        if self.on_settled:
            self.on_settled(j)

    def register_external(self, *, kind: str, label: str, owner: str, cancel: Callable[[], Any] | None,
                          idempotent: bool = False, meta: dict | None = None) -> Job:
        jid = f"job-{uuid.uuid4().hex[:10]}"
        j = Job(id=jid, kind=kind, label=label[:200], owner=owner, idempotent=idempotent, meta=meta or {})
        self.jobs[jid] = j
        if cancel:
            self.cancels[jid] = cancel
        self._save()
        return j

    async def kill(self, jid: str) -> dict:
        j = self.jobs.get(jid)
        if not j:
            raise KeyError(jid)
        if j.status != "running":
            return j.view()
        c = self.cancels.get(jid)
        if c:
            r = c()
            if asyncio.iscoroutine(r):
                await r
        t = self.tasks.get(jid)
        if t:
            t.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(t), 10)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):  # noqa: BLE001
                pass
        return j.view()

    def list(self, owner: str | None = None, running_only: bool = False) -> list[dict]:
        out = [j.view() for j in self.jobs.values() if (not owner or j.owner == owner)
               and (not running_only or j.status == "running")]
        return sorted(out, key=lambda v: v["started"], reverse=True)[:50]

    async def shutdown(self) -> None:
        """Engine stopping: running jobs stay `running` in the file, so the next process reports them lost."""
        self.stopping = True
        for jid, c in list(self.cancels.items()):
            try:
                r = c()
                if asyncio.iscoroutine(r):
                    await asyncio.wait_for(r, 5)
            except Exception:  # noqa: BLE001
                pass
        for t in list(self.tasks.values()):
            t.cancel()
