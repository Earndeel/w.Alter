"""Reacting to the agents' work: which sessions are kept, the idle deadline before reading, stopping on a pause,
the catch-up of past sessions (idempotent), commits attached to cards. walter-memory, walter-router and the gateway
are simulated; git and the database are real."""
import json
import subprocess

import pytest

from walter_devboard import backfill, cards, consumer, due, reading
from walter_devboard.config import Config

CFG = Config(dev_cwds=["/srv/dev"], idle_minutes=30)
CC = "claude_code/vm/aaa"
CX = "codex/vm/bbb"


@pytest.fixture(autouse=True)
def modules(monkeypatch):
    monkeypatch.setattr(cards, "known_modules", lambda: {"context", "memory", "router", "ops", "core"})


@pytest.fixture
def logs(monkeypatch):
    """Sessions known to walter-memory, by id; codex thread ids resolve to their session."""
    known = {CC: {"session_id": CC, "runtime": "claude_code", "cwd": "/srv/dev", "title": "tableau",
                  "last_event_at": "2026-11-10T10:00:00+00:00"},
             CX: {"session_id": CX, "runtime": "codex", "cwd": "/tmp", "title": "codex",
                  "last_event_at": "2026-11-09T10:00:00+00:00"}}

    def lookup(ref, runtime):
        return next((s for s in known.values() if s["runtime"] == runtime and ref in s["session_id"]), None)
    monkeypatch.setattr(consumer, "_lookup", lookup)
    monkeypatch.setattr(backfill, "_sessions", lambda runtime, since: [s for s in known.values()
                                                                       if s["runtime"] == runtime])
    monkeypatch.setattr(backfill, "_tasks", lambda: [])
    monkeypatch.setattr(due, "_tasks", lambda: [])
    monkeypatch.setattr(due, "commit_repos", lambda cfg: [])
    return known


def ev(type_, source, subject):
    return {"id": 1, "type": type_, "source": source, "subject": subject, "payload": {}}


def sessions(conn):
    return {r["session_id"]: r for r in conn.execute("select * from devboard.sessions")}


def test_claude_code_outside_dev_dir_ignored(conn, logs):
    logs[CC]["cwd"] = "/opt/walter-profiles/claude-code"
    consumer.on_event(CFG, conn, ev("turn.ended", "claude_code", CC))
    assert conn.execute("select count(*) n from devboard.live").fetchone()["n"] == 0
    row = sessions(conn).get(CC)
    assert row is None or (row["eligible"] is False and row["dirty"] is False)


def test_hermes_and_dsh_ignored(conn, logs, monkeypatch):
    monkeypatch.setattr(consumer, "_lookup", lambda *a: pytest.fail("no lookup for other runtimes"))
    consumer.on_event(CFG, conn, ev("turn.ended", "hermes", "hermes/x"))
    consumer.on_event(CFG, conn, ev("session.ended", "dsh", "dsh/y"))
    assert sessions(conn) == {}


def test_turn_marks_dirty_and_live(conn, logs):
    consumer.on_event(CFG, conn, ev("turn.ended", "claude_code", CC))
    consumer.on_event(CFG, conn, ev("turn.ended", "codex", "bbb"))      # codex subject = thread id
    s = sessions(conn)
    assert s[CC]["dirty"] and s[CC]["eligible"] and s[CC]["last_turn_at"] is not None
    assert s[CX]["dirty"]
    live = {r["session_id"] for r in conn.execute("select session_id from devboard.live")}
    assert live == {CC, CX}


def test_unknown_session_is_retried_later(conn, monkeypatch):
    monkeypatch.setattr(consumer, "_lookup", lambda *a: None)
    with pytest.raises(LookupError):         # the bus retries it once walter-logs has synced the session
        consumer.on_event(CFG, conn, ev("turn.ended", "claude_code", CC))


@pytest.fixture
def reads(monkeypatch):
    done = []

    def fake(cfg, conn, sid):
        done.append(sid)
        return "done"
    monkeypatch.setattr(reading, "read_session", fake)
    return done


def test_due_waits_idle_minutes(conn, logs, reads):
    consumer.on_event(CFG, conn, ev("turn.ended", "claude_code", CC))
    conn.execute("update devboard.sessions set last_turn_at = now() - interval '10 minutes'")
    due.run(CFG, conn)
    assert reads == []
    conn.execute("update devboard.sessions set last_turn_at = now() - interval '31 minutes'")
    due.run(CFG, conn)
    assert reads == [CC]


def test_due_stops_on_pause(conn, logs, monkeypatch):
    for s in (CC, CX):
        conn.execute("""insert into devboard.sessions (session_id, runtime, dirty, last_turn_at)
                        values (%s, %s, true, now() - interval '1 hour')""", (s, s.split("/")[0]))
    called = []
    monkeypatch.setattr(reading, "read_session", lambda cfg, c, sid: called.append(sid) or "paused")
    out = due.run(CFG, conn)
    assert len(called) == 1 and out["paused"]


def test_due_prunes_old_live(conn, logs, reads):
    conn.execute("insert into devboard.live (session_id, runtime, at) values ('x', 'codex', now() - interval '11 minutes')")
    conn.execute("insert into devboard.live (session_id, runtime, at) values ('y', 'codex', now())")
    due.run(CFG, conn)
    assert [r["session_id"] for r in conn.execute("select session_id from devboard.live")] == ["y"]


def test_backfill_idempotent(conn, logs, router, gateway, monkeypatch):
    digest = {"session": {"runtime": "x", "title": "t"}, "from_seq": 1, "to_seq": 4, "more": False,
              "items": [{"seq": 2, "at": "2026-11-10 10:00:00+00:00", "kind": "user", "text": "fais le lot 3"}]}
    monkeypatch.setattr(reading, "_digest", lambda sid, after: digest if after == 0 else {**digest, "items": [],
                                                                                          "from_seq": 5, "to_seq": 4})
    answer = {"is_walter_development": True, "approvals": [], "cards": [
        {"ref": None, "title": "Mémoire : lot 3", "module": "memory", "status": "in_progress", "owner": "codex",
         "change": "x", "deadline": None, "decisions": [], "files": [], "blocks": [],
         "evidence": [{"seq": 2, "quote": "fais le lot 3"}]}]}
    gateway["answers"] = [(json.dumps(answer), "claude-pro/m")] * 2
    first = backfill.run(CFG, conn, since="2026-10-01", limit=20)
    assert first["read"] == 2 and len(gateway["posts"]) == 2
    conn.execute("update devboard.sessions set dirty = true, read_seq = 0")   # even if asked to re-read
    backfill.run(CFG, conn, since="2026-10-01", limit=20)
    assert len(gateway["posts"]) == 2                                           # everything came from the memo
    assert conn.execute("select count(*) n from devboard.cards").fetchone()["n"] == 1


def test_backfill_keeps_only_dev_sessions(conn, logs, monkeypatch):
    logs[CC]["cwd"] = "/elsewhere"
    monkeypatch.setattr(reading, "read_session", lambda *a: "done")
    backfill.run(CFG, conn, since="2026-10-01", limit=0)
    s = sessions(conn)
    assert s[CC]["eligible"] is False and s[CX]["eligible"] is True and s[CX]["dirty"] is True


def test_due_records_commits(conn, logs, reads, tmp_path, monkeypatch):
    cards.apply(conn, CC, 1, 9, {"is_walter_development": True, "approvals": [], "cards": [
        {"ref": None, "title": "Tableau", "module": "ops", "status": "in_progress", "owner": "claude_code",
         "change": "x", "deadline": None, "decisions": [], "files": [], "blocks": [],
         "evidence": [{"seq": 3, "quote": "q"}]}]})
    repo = tmp_path / "ops"
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "a").write_text("1")
    subprocess.run(git + ["add", "a"], check=True)
    subprocess.run(git + ["commit", "-qm", "W-1 : premier écran du tableau"], check=True)
    (repo / "b").write_text("2")
    subprocess.run(git + ["add", "b"], check=True)
    subprocess.run(git + ["commit", "-qm", "sans numéro"], check=True)
    monkeypatch.setattr(due, "commit_repos", lambda cfg: [repo])
    due.run(CFG, conn)
    due.run(CFG, conn)                                                  # twice: no duplicate
    rows = conn.execute("""select a.card_id, a.text from devboard.activity a where kind = 'commit'
                           order by a.card_id nulls last""").fetchall()
    assert [(r["card_id"], r["text"]) for r in rows] == [(1, "ops : W-1 : premier écran du tableau"),
                                                         (None, "ops : sans numéro")]
    assert conn.execute("select count(*) n from devboard.card_evidence where kind = 'commit'").fetchone()["n"] == 1


def test_due_leaves_pause_marker(conn, logs, monkeypatch):
    conn.execute("""insert into devboard.sessions (session_id, runtime, dirty, last_turn_at)
                    values (%s, 'claude_code', true, now() - interval '1 hour')""", (CC,))
    monkeypatch.setattr(reading, "read_session", lambda *a: "paused")
    due.run(CFG, conn)
    assert conn.execute("select value from devboard.state where key = 'pause'").fetchone()["value"]["what"] == "session"
    monkeypatch.setattr(reading, "read_session", lambda *a: "done")
    due.run(CFG, conn)
    assert conn.execute("select value from devboard.state where key = 'pause'").fetchone()["value"] is None


def test_replayed_old_event_marks_dirty_but_not_live(conn, logs):
    """Catch-up after a restart replays old turns: they are read later, but never shown as live work."""
    from datetime import datetime, timedelta, timezone
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    conn.execute("insert into devboard.sessions (session_id, runtime, eligible) values (%s, 'codex', true)", (CX,))
    consumer.on_event(CFG, conn, {**ev("turn.ended", "codex", "bbb"), "at": old})
    s = conn.execute("select dirty, last_turn_at from devboard.sessions where session_id = %s", (CX,)).fetchone()
    assert s["dirty"] and abs((s["last_turn_at"] - old).total_seconds()) < 1
    assert conn.execute("select count(*) n from devboard.live").fetchone()["n"] == 0
    consumer.on_event(CFG, conn, {**ev("turn.ended", "codex", "bbb"), "at": datetime.now(timezone.utc)})
    assert conn.execute("select count(*) n from devboard.live").fetchone()["n"] == 1


def test_old_event_of_unknown_session_is_skipped_without_lookup(conn, logs, monkeypatch):
    """History is the backfill's job: an old turn of a session never registered costs no lookup and no retry."""
    from datetime import datetime, timedelta, timezone
    called = []
    monkeypatch.setattr(consumer, "_lookup", lambda ref, runtime: called.append(ref))
    old = datetime.now(timezone.utc) - timedelta(days=20)
    consumer.on_event(CFG, conn, {**ev("turn.ended", "codex", "never-logged"), "at": old})
    assert called == [] and conn.execute("select count(*) n from devboard.sessions").fetchone()["n"] == 0
    with pytest.raises(LookupError):                       # a fresh one waits for walter-logs (bus retry)
        consumer.on_event(CFG, conn, {**ev("turn.ended", "codex", "never-logged"), "at": datetime.now(timezone.utc)})


def test_one_broken_session_never_stops_the_others(conn, logs, monkeypatch):
    """Review I3: a purged session (digest error) or a timeout is recorded and skipped; the pass goes on."""
    from walter_devboard import status
    for s in (CC, CX):
        conn.execute("""insert into devboard.sessions (session_id, runtime, dirty, last_turn_at)
                        values (%s, %s, true, now() - interval '1 hour')""", (s, s.split("/")[0]))
    read = []

    def fake(cfg, c, sid):
        read.append(sid)
        if sid == CC:
            raise LookupError("session inconnue")
        return "done"
    monkeypatch.setattr(reading, "read_session", fake)
    out = due.run(CFG, conn)
    assert read == [CC, CX] and out["sessions"][CC] == "error" and out["paused"] is None
    assert "session inconnue" in status.report(conn)["text"]
    for _ in range(2):
        due.run(CFG, conn)
    read.clear()
    due.run(CFG, conn)                                    # set aside after 3 errors
    assert CC not in read


def test_digest_error_answer_is_an_error():
    import subprocess
    from walter_devboard import reading as r
    class Out:
        stdout = '{"error": "session inconnue"}'
    orig = subprocess.run
    subprocess.run = lambda *a, **k: Out()
    try:
        with pytest.raises(LookupError, match="session inconnue"):
            r._digest("codex/x", 0)
    finally:
        subprocess.run = orig


def test_codex_in_an_excluded_folder_is_not_read(conn, logs, monkeypatch):
    """Review I7: W.Alter's personal mode (a profile folder) is never read, even for Codex."""
    cfg = Config(dev_cwds=["/srv/dev"], excluded_cwds=["/srv/profiles"])
    logs[CX]["cwd"] = "/srv/profiles/codex"
    consumer.on_event(cfg, conn, ev("turn.ended", "codex", "bbb"))
    assert sessions(conn)[CX]["eligible"] is False
    assert conn.execute("select count(*) n from devboard.live").fetchone()["n"] == 0
    conn.execute("delete from devboard.sessions")
    monkeypatch.setattr(reading, "read_session", lambda *a: "done")
    backfill.run(cfg, conn, since="2026-10-01", limit=0)
    assert sessions(conn)[CX]["eligible"] is False
