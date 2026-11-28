"""`walter-devboard status`: what the board is waiting on, in plain words (pause, failed reads, sessions to read)."""
import json

from walter_devboard import status


def test_status_reports_pause_failed_and_queue(conn):
    conn.execute("""insert into devboard.state (key, value) values ('pause', %s)""",
                 (json.dumps({"what": "session", "at": "2026-11-14T10:00:00+00:00"}),))
    conn.execute("""insert into devboard.readings (key, kind, source_ref, prompt_version, status, attempts, error)
                    values ('k1', 'session', 'codex/x', '1', 'failed', 4, 'bad json'),
                           ('k2', 'session', 'codex/y', '1', 'done', 1, null)""")
    conn.execute("""insert into devboard.sessions (session_id, runtime, eligible, dirty) values
                    ('codex/x', 'codex', true, true), ('codex/z', 'codex', false, true), ('codex/w', 'codex', true, false)""")
    s = status.report(conn)
    assert s["pause"]["what"] == "session" and "en pause : quota Claude Pro" in s["text"]
    assert s["readings"] == {"done": 1, "failed": 1} and s["failed"][0]["source_ref"] == "codex/x"
    assert s["sessions"] == {"eligible": 2, "to_read": 1}


def test_status_without_pause(conn):
    s = status.report(conn)
    assert s["pause"] is None and "en pause" not in s["text"]
