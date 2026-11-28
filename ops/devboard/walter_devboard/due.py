"""`walter-devboard due` (timer, every 10 min = the deadline): read the sessions idle for `idle_minutes`, the new or
changed decisions, the owner's tasks changed since the last pass; record the module repositories' new commits;
drop stale live rows. The first pause (quota, route) stops the model work until the next pass."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import config, db, reading
from .config import Config

REF = re.compile(r"\bW-(\d+)\b")


def _state(conn, key: str, default=None):
    r = conn.execute("select value from devboard.state where key = %s", (key,)).fetchone()
    return r["value"] if r else default


def _put(conn, key: str, value) -> None:
    conn.execute("""insert into devboard.state (key, value, at) values (%s, %s, now())
                    on conflict (key) do update set value = excluded.value, at = now()""", (key, json.dumps(value)))


def _tasks() -> list[dict]:
    out = subprocess.run(["walter-memory", "tasks", "list", "--status", "all", "--limit", "50"], capture_output=True,
                         text=True, check=True, timeout=120).stdout
    rows = json.loads(out)
    return rows if isinstance(rows, list) else rows.get("tasks", [])


MAX_ERRORS = 3          # a source failing this many passes in a row is set aside (shown by `status`)


def guarded(conn, ref: str, read) -> str:
    """Run one reading; an exception (purged session, timeout, bug) is recorded under `ref` and never stops the
    pass. Returns the reading's state or 'error'."""
    errors = _state(conn, "errors", {}) or {}
    try:
        st = read()
    except Exception as e:                                # noqa: BLE001 — one source must not stop the others
        e_ = errors.get(ref, {})
        errors[ref] = {"n": e_.get("n", 0) + 1, "error": f"{type(e).__name__}: {e}"[:300],
                       "at": datetime.now(timezone.utc).isoformat()}
        _put(conn, "errors", errors)
        return "error"
    if ref in errors:
        errors.pop(ref)
        _put(conn, "errors", errors)
    return st


def set_aside(conn) -> list[str]:
    return [k for k, v in (_state(conn, "errors", {}) or {}).items() if v.get("n", 0) >= MAX_ERRORS]


def read_tasks(cfg: Config, conn, tasks: list[dict]) -> str | None:
    """Each task once per version (updated_at); returns 'paused' when the model must wait."""
    seen = _state(conn, "tasks", {}) or {}
    try:
        for t in tasks:
            stamp = str(t.get("updated_at"))
            if seen.get(t["task_id"]) == stamp:
                continue
            ref = f"task:{t['task_id']}"
            if ref in set_aside(conn):
                continue
            st = guarded(conn, ref, lambda: reading.read_task(cfg, conn, t))
            if st == "paused":
                return "paused"
            if st in ("done", "skipped"):
                seen[t["task_id"]] = stamp
    finally:
        _put(conn, "tasks", seen)
    return None


def commit_repos(cfg: Config) -> list[Path]:
    """Git repositories of the modules (layout roots) and of the global docs, each once."""
    out, seen = [], set()
    for root in [*config.module_roots(), cfg.docs_dir]:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        top = r.stdout.strip()
        if r.returncode == 0 and top and top not in seen:
            seen.add(top)
            out.append(Path(top))
    return out


def record_commits(cfg: Config, conn) -> int:
    since = _state(conn, "commits_at") or cfg.since
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for repo in commit_repos(cfg):
        r = subprocess.run(["git", "-C", str(repo), "log", f"--since={since}", "--no-merges", "-n", "500",
                            "--format=%H%x1f%cI%x1f%s"], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            sha, at, subject = (line.split("\x1f") + ["", ""])[:3]
            src = f"{repo.name}@{sha[:12]}"
            if conn.execute("select 1 from devboard.activity where kind = 'commit' and source_ref = %s",
                            (src,)).fetchone():
                continue
            card = None
            for n in REF.findall(subject):
                card = conn.execute("select id from devboard.cards where id = %s", (int(n),)).fetchone()
                if card:
                    break
            conn.execute("""insert into devboard.activity (at, kind, source_ref, card_id, text)
                            values (%s, 'commit', %s, %s, %s)""",
                         (at, src, card["id"] if card else None, f"{repo.name} : {subject}"[:500]))
            if card:
                conn.execute("""insert into devboard.card_evidence (card_id, kind, source_ref, quote, at)
                                values (%s, 'commit', %s, %s, %s)""", (card["id"], src, subject[:400], at))
                conn.execute("""update devboard.cards set last_activity_at = greatest(last_activity_at, %s)
                                where id = %s""", (at, card["id"]))
            added += 1
    _put(conn, "commits_at", now)
    if added:
        db.notify(conn, "commits", count=added)
    return added


def run(cfg: Config, conn) -> dict:
    out = _run(cfg, conn)
    _put(conn, "pause", {"what": out["paused"], "at": datetime.now(timezone.utc).isoformat()} if out["paused"] else None)
    return out


def _run(cfg: Config, conn) -> dict:
    out = {"sessions": {}, "decisions": {}, "tasks": None, "commits": 0, "paused": None}
    conn.execute("delete from devboard.live where at < now() - interval '10 minutes'")
    out["commits"] = record_commits(cfg, conn)
    aside = set_aside(conn)
    rows = conn.execute("""select session_id from devboard.sessions
                           where eligible and dirty and not (session_id = any(%s))
                             and (state = 'ended' or last_turn_at < now() - make_interval(mins => %s))
                           order by last_turn_at limit %s""",
                        (aside, cfg.idle_minutes, cfg.sessions_per_pass)).fetchall()
    for r in rows:
        st = guarded(conn, r["session_id"], lambda: reading.read_session(cfg, conn, r["session_id"]))
        out["sessions"][r["session_id"]] = st
        if st == "paused":
            out["paused"] = "session"
            return out
    for r in conn.execute("""select id, anchor from devboard.decisions
                             where removed_at is null and read_sha256 is distinct from sha256
                               and not ('decision:' || anchor = any(%s))
                             order by date desc, id desc limit %s""", (aside, cfg.sessions_per_pass)).fetchall():
        st = guarded(conn, f"decision:{r['anchor']}", lambda: reading.read_decision(cfg, conn, r["id"]))
        out["decisions"][r["anchor"]] = st
        if st == "paused":
            out["paused"] = "decision"
            return out
    out["tasks"] = read_tasks(cfg, conn, _tasks()) or "done"
    if out["tasks"] == "paused":
        out["paused"] = "task"
    return out
