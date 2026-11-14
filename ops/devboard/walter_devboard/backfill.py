"""`walter-devboard backfill [--since] [--limit]`: register the development sessions since `since`, read the owner's
tasks, then read at most `limit` sessions, oldest first, with the same guards as `due`. Idempotent: readings are
memoized and each session keeps its read position."""
from __future__ import annotations

import json
import subprocess

from . import due, reading
from .config import Config


def _sessions(runtime: str, since: str) -> list[dict]:
    out = subprocess.run(["walter-memory", "logs", "sessions", "--runtime", runtime, "--since", since, "--limit",
                          "2000", "--cloud-safe", "--json"], capture_output=True, text=True, check=True,
                         timeout=120).stdout
    rows = json.loads(out)
    return rows if isinstance(rows, list) else rows.get("sessions", [])


def _tasks() -> list[dict]:
    return due._tasks()


def run(cfg: Config, conn, since: str | None = None, limit: int = 20) -> dict:
    since = since or cfg.since
    registered = 0
    for runtime in ("claude_code", "codex"):
        for s in _sessions(runtime, since):
            if ":" in s["session_id"]:                   # sub-agent of a session: its parent carries the result
                continue
            eligible = runtime == "codex" or s.get("cwd") in cfg.dev_cwds
            r = conn.execute("""insert into devboard.sessions (session_id, runtime, title, cwd, eligible, dirty,
                                                               last_turn_at)
                                values (%s, %s, %s, %s, %s, %s, %s) on conflict (session_id) do nothing""",
                             (s["session_id"], runtime, s.get("title"), s.get("cwd"), eligible, eligible,
                              s.get("last_event_at") or s.get("started_at")))
            registered += r.rowcount
    out = {"registered": registered, "read": 0, "results": {}, "paused": None}
    if due.read_tasks(cfg, conn, _tasks()) == "paused":
        out["paused"] = "task"
        return out
    for r in conn.execute("""select session_id from devboard.sessions where eligible and dirty
                             order by last_turn_at nulls first limit %s""", (limit,)).fetchall():
        st = reading.read_session(cfg, conn, r["session_id"])
        out["results"][r["session_id"]] = st
        if st == "paused":
            out["paused"] = "session"
            break
        out["read"] += 1
    return out
