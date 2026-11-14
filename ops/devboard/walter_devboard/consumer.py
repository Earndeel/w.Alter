"""Bus consumer `devboard`: an agent turn (turn.ended / session.ended) marks its session to be read once it has been
idle for `idle_minutes` (walter-devboard due), and shows it as live work. Kept: Codex sessions, and Claude Code
sessions opened in one of the instance's `dev_cwds`. Every other runtime (the W.Alter engine, Hermes…) is ignored."""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone

from . import db
from .config import Config, load

SOURCES = ("claude_code", "codex")
TYPES = ("turn.ended", "session.ended")
LIVE_FOR = timedelta(minutes=10)                 # = the prune of devboard.live in due
log = logging.getLogger("walter.devboard")


def _lookup(ref: str, runtime: str) -> dict | None:
    """The walter-logs session behind a bus subject (Claude Code: the session id; Codex: its thread id)."""
    out = subprocess.run(["walter-memory", "logs", "sessions", ref, "--runtime", runtime, "--limit", "5",
                          "--cloud-safe", "--json"], capture_output=True, text=True, check=True, timeout=60).stdout
    rows = json.loads(out)
    rows = rows if isinstance(rows, list) else rows.get("sessions", [])
    return next((r for r in rows if r["session_id"] == ref or r["session_id"].endswith("/" + ref)), None)


def _cached(conn, subject: str, runtime: str):
    return conn.execute("""select * from devboard.sessions where session_id = %s
                           or (runtime = %s and session_id like '%%/' || %s) limit 1""",
                        (subject, runtime, subject)).fetchone()


def on_event(cfg: Config, conn, ev: dict) -> None:
    source, subject = ev.get("source"), ev.get("subject")
    if source not in SOURCES or not subject or ":" in subject:      # ':' = a sub-agent of a session
        return
    row = _cached(conn, subject, source)
    if row is None:
        s = _lookup(subject, source)
        if s is None:
            raise LookupError(f"{source} session {subject} not in walter-logs yet")
        if ":" in s["session_id"]:
            return
        eligible = source == "codex" or s.get("cwd") in cfg.dev_cwds
        conn.execute("""insert into devboard.sessions (session_id, runtime, title, cwd, eligible)
                        values (%s, %s, %s, %s, %s) on conflict (session_id) do nothing""",
                     (s["session_id"], source, s.get("title"), s.get("cwd"), eligible))
        row = _cached(conn, s["session_id"], source)
    if not row["eligible"]:
        return
    sid = row["session_id"]
    at = ev.get("at") or datetime.now(timezone.utc)
    conn.execute("""update devboard.sessions set dirty = true,
                      last_turn_at = greatest(coalesce(last_turn_at, %s), %s),
                      state = case when %s = 'session.ended' then 'ended' else state end
                    where session_id = %s""", (at, at, ev.get("type"), sid))
    if at < datetime.now(timezone.utc) - LIVE_FOR:      # a replayed old turn (catch-up): read later, not live
        return
    conn.execute("""insert into devboard.live (session_id, runtime, title, card_id, at)
                    values (%s, %s, %s, (select card_id from devboard.card_evidence where source_ref = %s
                                         order by id desc limit 1), %s)
                    on conflict (session_id) do update set at = greatest(devboard.live.at, excluded.at),
                      title = excluded.title, card_id = coalesce(excluded.card_id, devboard.live.card_id)""",
                 (sid, row["runtime"], row["title"], sid, at))
    db.notify(conn, "live", session=sid)


def main() -> None:
    from walter_memory.bus import Consumer
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load()

    def handle(ev: dict) -> None:
        with db.connection() as conn:
            on_event(cfg, conn, ev)
    Consumer("devboard", TYPES).run(handle)


if __name__ == "__main__":
    main()
