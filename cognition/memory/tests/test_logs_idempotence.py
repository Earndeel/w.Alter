"""walter-logs idempotence on the event's identity (2026-10-25): a transcript re-read from scratch, rewritten (offsets
shifted) or re-appended by its runtime, and Hermes rows re-persisted under new ids, add zero duplicates.
Real PostgreSQL (migration 015), one transaction rolled back at the end: nothing stays in walter_logs."""
import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory import ingestion, logs as L  # noqa: E402
from walter_memory.db import connect  # noqa: E402

SID = f"pytest-{uuid.uuid4().hex[:12]}"
SESSION = f"claude_code/vm/{SID}"


@pytest.fixture
def conn(monkeypatch):
    c = connect()
    # checkpoints read inside the test transaction (the pooled reader would not see them)
    monkeypatch.setattr(ingestion, "get_checkpoint", lambda connector, stream="": (c.execute(
        "select cursor from ingestion.checkpoints where connector = %s and stream = %s", (connector, stream)).fetchone()
        or {"cursor": {}})["cursor"])
    yield c
    c.rollback()
    c.close()


def line(uuid_, kind, ts, content, **extra):
    return {"type": kind, "uuid": uuid_, "sessionId": SID, "timestamp": ts, "message": {"content": content,
            **({"model": "claude-x", "id": "msg_" + uuid_} if kind == "assistant" else {})}, **extra}


TURN1 = [
    line("u1", "user", "2026-10-25T10:00:00.000Z", "Liste les fichiers", origin={"kind": "human"}),
    line("a1", "assistant", "2026-10-25T10:00:01.000Z", [{"type": "thinking", "thinking": "je lance ls"},
                                                       {"type": "tool_use", "id": "t1", "name": "Bash",
                                                        "input": {"command": "ls"}}]),
    line("r1", "user", "2026-10-25T10:00:02.000Z", [{"type": "tool_result", "tool_use_id": "t1", "content": "a.txt"}]),
    line("a2", "assistant", "2026-10-25T10:00:03.000Z", [{"type": "text", "text": "Un fichier : a.txt"}]),
]
TURN2 = [line("u2", "user", "2026-10-25T10:05:00.000Z", "Et maintenant ?", origin={"kind": "human"}),
         line("a3", "assistant", "2026-10-25T10:05:01.000Z", [{"type": "text", "text": "Rien d'autre."}])]


def write(path: Path, lines: list[dict]) -> None:
    path.write_text("".join(json.dumps(d) + "\n" for d in lines))


def events(conn) -> list[dict]:
    return conn.execute("select seq, type, turn, text, event_key from walter_logs.events where session_id = %s order by seq",
                        (SESSION,)).fetchall()


def test_rewritten_and_reappended_transcript_adds_no_duplicate(conn, tmp_path, monkeypatch):
    root = tmp_path / "projects"
    path = root / "-root" / f"{SID}.jsonl"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(L, "ROOTS", {**L.ROOTS, "claude": root})

    write(path, TURN1)
    assert L.sync_transcript(conn, "claude", path)["inserted"] == 5
    first = events(conn)
    assert [e["type"] for e in first] == ["user/message", "assistant/reasoning", "tool/call", "tool/result",
                                          "assistant/message"]
    assert all(e["event_key"] for e in first)

    # the runtime re-appends earlier lines (resume) after the new turn: only the new turn is new
    write(path, TURN1 + TURN2 + TURN1)
    assert L.sync_transcript(conn, "claude", path)["inserted"] == 2

    # the transcript is rewritten shorter (compaction): offsets shift, read again from 0 → nothing new
    write(path, [{"type": "summary", "summary": "x"}] + TURN1 + TURN2)
    assert L.sync_transcript(conn, "claude", path)["inserted"] == 0

    # the checkpoint is lost (path alias, reset): a full re-read from scratch → nothing new
    conn.execute("delete from ingestion.checkpoints where connector = %s and stream like %s", (L.CONNECTOR, f"%{SID}%"))
    assert L.sync_transcript(conn, "claude", path)["inserted"] == 0

    got = events(conn)
    assert len(got) == 7 and len({e["event_key"] for e in got}) == 7
    assert [e["text"] for e in got if e["type"] == "user/message"] == ["Liste les fichiers", "Et maintenant ?"]
    assert max(e["turn"] for e in got) == 2                              # a re-read human message is not a new turn
    assert conn.execute("select turns from walter_logs.sessions where session_id = %s", (SESSION,)).fetchone()["turns"] == 2


def test_hermes_row_repersisted_under_a_new_id_is_one_event(conn):
    """Hermes re-writes history rows in state.db with new ids (m764, m919, m1168: same call, same instant)."""
    sid = f"hermes/pytest/{SID}"
    w = L.Writer(conn)
    w.session(sid, runtime="hermes", native_id=SID, profile="pytest")
    ts = L._ts(1787229836.4170914)
    for mid in (764, 919, 1168):
        w.add(sid, "tool/call", ts, f"m{mid}:call:call_4E", call_id="call_4E", tool="terminal", text='{"cmd": "ls"}')
        w.add(sid, "tool/result", ts, f"m{mid + 1}", call_id="call_4E", tool="terminal", text="ok", status="ok")
    assert w.flush() == 2
    w2 = L.Writer(conn)             # a later pass (new Writer, keys already stored)
    w2.session(sid, runtime="hermes", native_id=SID, profile="pytest")
    w2.add(sid, "tool/result", ts, "m2000", call_id="call_4E", tool="terminal", text="ok", status="ok")
    w2.add(sid, "tool/result", ts, "m2001", call_id="call_4E", tool="terminal", text="ok (2)", status="ok")
    assert w2.flush() == 1
    assert [r["seq"] for r in conn.execute("select seq from walter_logs.events where session_id = %s order by seq",
                                           (sid,)).fetchall()] == [1, 2, 3]


def test_stored_rows_give_back_the_same_key(conn, tmp_path, monkeypatch):
    """The backfill (connectors/walter_logs.py keys) recomputes event_key from stored rows: jsonb round trip included."""
    root = tmp_path / "projects"
    path = root / "-root" / f"{SID}.jsonl"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(L, "ROOTS", {**L.ROOTS, "claude": root})
    write(path, TURN1 + [{"type": "attachment", "uuid": "x1", "sessionId": SID, "timestamp": "2026-10-25T10:00:04.5Z",
                          "attachment": {"type": "hook_additional_context", "content": "ctx", "hookName": "H",
                                         "ratio": 2.0, "tiny": 1e-07, "big": 1e16}}])
    L.sync_transcript(conn, "claude", path)
    w = L.Writer(conn)
    w.session(SESSION, runtime="claude_code", native_id=SID)
    w.add(SESSION, "step/end", None, "o5000", data={"ratio": 2.0, "tiny": 1e-07, "big": 1e16, "deep": [1.5, {"a": None}],
                                                    "when": L._ts(TURN1[0]["timestamp"]), "é": "ü"})
    w.flush()
    stored = {e["seq"]: e["event_key"] for e in events(conn)}
    conn.execute("update walter_logs.events set event_key = null where session_id = %s", (SESSION,))
    # a later copy without key (as left by the old ingestion) is reported, never keyed
    conn.execute("""insert into walter_logs.events (session_id, seq, type, occurred_at, text, data, privacy_class, source_ref)
                    select session_id, 100, type, occurred_at, text, data, privacy_class, 'o999' from walter_logs.events
                    where session_id = %s and seq = 1""", (SESSION,))
    todo, dups = L.session_keys(conn, SESSION)
    assert dict((seq, k) for k, seq in todo) == stored
    assert dups == [(100, 1)]
    for k, seq in todo:          # what `walter_logs.py keys` does
        conn.execute("update walter_logs.events set event_key = %s where session_id = %s and seq = %s", (k, SESSION, seq))
    # the old one-off quarantine (2026-10-25) is gone with walter_logs.duplicates (cleanup phase 2): the writer never
    # creates such copies, `keys` only reports them
    assert L.session_keys(conn, SESSION)[1] == [(100, 1)]
