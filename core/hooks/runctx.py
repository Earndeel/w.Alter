"""Current Walter run of a harness process — an adapter detail (Monsieur, 2026-10-27).

The run_id is Walter's canonical identifier; how a tool process learns it depends on the harness:
  * an explicit WALTER_RUN_ID in the environment wins (walter_run sub-agents, DSH, any runtime that can pass it);
  * Claude Code (and runtimes that spawn hooks and MCP servers from the same process) cannot pass it to the MCP
    server, so the hook records the run under its parent PID and the MCP server, a child of that same process,
    reads it back. Verified 2026-10-27: hooks and the walter-core MCP server share the Claude Code process as parent.
Files: <instance>/state/runs/current/<pid>.json (0600), one per harness process, overwritten at each message.
Stdlib only: loaded by the hook (walter-python) and by the MCP server (core venv).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

POINTER = Path("/etc/walter/instance")
STALE_S = 6 * 3600


def _dir() -> Path:
    root = os.environ.get("WALTER_INSTANCE")
    if not root:
        try:
            root = POINTER.read_text().strip()
        except OSError:
            root = "/instances/monsieur"
    return Path(root) / "state" / "runs" / "current"


def record(pid: int, run_id: str, session_id: str, runtime: str) -> None:
    d = _dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = d / f".{pid}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"run_id": run_id, "session_id": session_id, "runtime": runtime, "at": time.time()}, f)
    os.replace(tmp, d / f"{pid}.json")


def current(pid: int | None = None) -> dict | None:
    """The run of this process' harness: explicit environment first, else the record of the parent process."""
    if os.environ.get("WALTER_RUN_ID"):
        return {"run_id": os.environ["WALTER_RUN_ID"], "session_id": os.environ.get("WALTER_SESSION_ID"),
                "task_id": os.environ.get("WALTER_TASK_ID")}
    try:
        data = json.loads((_dir() / f"{pid or os.getppid()}.json").read_text())
    except (OSError, ValueError):
        return None
    return data if time.time() - float(data.get("at", 0)) < STALE_S else None


def env(pid: int | None = None) -> dict[str, str]:
    """Environment entries that carry the current run to a child process (empty outside a run)."""
    cur = current(pid) or {}
    out = {"WALTER_RUN_ID": cur.get("run_id"), "WALTER_SESSION_ID": cur.get("session_id"),
           "WALTER_TASK_ID": cur.get("task_id")}
    return {k: str(v) for k, v in out.items() if v}


def sweep(max_age_s: float = 7 * 86400) -> int:
    """Remove records of harness processes that no longer exist (called rarely, by the hook)."""
    n = 0
    for p in _dir().glob("*.json"):
        try:
            if not Path(f"/proc/{p.stem}").exists() or time.time() - p.stat().st_mtime > max_age_s:
                p.unlink()
                n += 1
        except (OSError, ValueError):
            pass
    return n


SKIP = {"sh", "bash", "dash", "zsh", "env", "timeout", "nice", "walter-python"}


def harness_pid(start: int | None = None) -> int:
    """The harness process above a hook: the nearest ancestor that is not a shell or an interpreter wrapper."""
    if os.environ.get("WALTER_HARNESS_PID", "").isdigit():   # a scenario runner standing in for a harness
        return int(os.environ["WALTER_HARNESS_PID"])
    pid = start or os.getppid()
    for _ in range(6):
        try:
            comm = Path(f"/proc/{pid}/comm").read_text().strip()
            if comm not in SKIP and not comm.startswith("python"):
                return pid
            ppid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return pid
        if ppid <= 1:
            return pid
        pid = ppid
    return pid
