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


def read_tasks(cfg: Config, conn, tasks: list[dict]) -> str | None:
    """Each task once per version (updated_at); returns 'paused' when the model must wait."""
    seen = _state(conn, "tasks", {}) or {}
    try:
        for t in tasks:
            stamp = str(t.get("updated_at"))
            if seen.get(t["task_id"]) == stamp:
                continue
            st = reading.read_task(cfg, conn, t)
            if st == "paused":
                return "paused"
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
    out = {"sessions": {}, "decisions": {}, "tasks": None, "commits": 0, "paused": None}
    conn.execute("delete from devboard.live where at < now() - interval '10 minutes'")
    out["commits"] = record_commits(cfg, conn)
    rows = conn.execute("""select session_id from devboard.sessions
                           where eligible and dirty
                             and (state = 'ended' or last_turn_at < now() - make_interval(mins => %s))
                           order by last_turn_at limit %s""", (cfg.idle_minutes, cfg.sessions_per_pass)).fetchall()
    for r in rows:
        st = reading.read_session(cfg, conn, r["session_id"])
        out["sessions"][r["session_id"]] = st
        if st == "paused":
            out["paused"] = "session"
            return out
    for r in conn.execute("""select id, anchor from devboard.decisions
                             where removed_at is null and read_sha256 is distinct from sha256
                             order by date desc, id desc limit %s""", (cfg.sessions_per_pass,)).fetchall():
        st = reading.read_decision(cfg, conn, r["id"])
        out["decisions"][r["anchor"]] = st
        if st == "paused":
            out["paused"] = "decision"
            return out
    out["tasks"] = read_tasks(cfg, conn, _tasks()) or "done"
    if out["tasks"] == "paused":
        out["paused"] = "task"
    return out
