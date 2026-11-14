"""walter-logs digest (2026-11-14, ops/devboard): a session condensed for a reader — the owner's messages, the last
answer of each turn, the files touched, compaction summaries — in slices bounded by characters, without gaps or
repeats. Real PostgreSQL test database, one transaction rolled back at the end."""
import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walter_memory import logs as L  # noqa: E402
from walter_memory.db import connect  # noqa: E402

NATIVE = f"pytest-{uuid.uuid4().hex[:12]}"
SID = f"claude_code/vm/{NATIVE}"


@pytest.fixture
def conn():
    c = connect()
    yield c
    c.rollback()
    c.close()


def session(conn, cwd="/root"):
    conn.execute("""insert into walter_logs.sessions (session_id, runtime, native_id, cwd, title, started_at, last_event_at)
                    values (%s, 'claude_code', %s, %s, 'essai', now(), now())""", (SID, NATIVE, cwd))


def ev(conn, seq, type_, text=None, turn=1, tool=None, data=None, privacy="cloud_allowed"):
    conn.execute("""insert into walter_logs.events (session_id, seq, type, occurred_at, turn, tool, text, data, chars,
                                                    privacy_class, source_ref)
                    values (%s, %s, %s, now() + make_interval(secs => %s), %s, %s, %s, %s, %s, %s, %s)""",
                 (SID, seq, type_, seq, turn, tool, text, json.dumps(data or {}), len(text or ""), privacy, f"pytest:{seq}"))


def two_turns(conn):
    session(conn)
    ev(conn, 1, "user/message", "Corrige le fichier a.py", turn=1)
    ev(conn, 2, "assistant/reasoning", "je réfléchis", turn=1)
    ev(conn, 3, "assistant/message", "Je regarde.", turn=1)
    ev(conn, 4, "tool/call", '{"file_path": "/x/a.py"}', turn=1, tool="Edit", data={"input": {"file_path": "/x/a.py"}})
    ev(conn, 5, "tool/result", "ok", turn=1, tool="Edit")
    ev(conn, 6, "assistant/message", "C'est corrigé.", turn=1)
    ev(conn, 7, "user/message", "Merci", turn=2)
    ev(conn, 8, "assistant/message", "De rien.", turn=2)


def test_sessions_include_cwd(conn):
    session(conn)
    rows = [s for s in L.sessions(conn, text=NATIVE) if s["session_id"] == SID]
    assert rows and rows[0]["cwd"] == "/root"


def test_digest_kinds_and_range(conn):
    two_turns(conn)
    d = L.digest(conn, SID, max_privacy="cloud_allowed")
    assert [i["kind"] for i in d["items"]] == ["user", "file", "assistant", "user", "assistant"]
    assert d["items"][1]["text"] == "Edit /x/a.py"
    assert d["items"][2]["text"] == "C'est corrigé."
    assert d["from_seq"] == 1 and d["to_seq"] == 8 and d["more"] is False
    assert d["session"]["cwd"] == "/root"


def test_digest_chunks(conn):
    session(conn)
    for i in range(1, 11):
        ev(conn, 2 * i - 1, "user/message", f"{i:02d}" + "x" * 48, turn=i)
        ev(conn, 2 * i, "assistant/message", "y" * 50, turn=i)
    first = L.digest(conn, SID, max_chars=200, max_privacy="cloud_allowed")
    assert first["more"] is True
    second = L.digest(conn, SID, after_seq=first["to_seq"], max_chars=200, max_privacy="cloud_allowed")
    seqs = [i["seq"] for i in first["items"]] + [i["seq"] for i in second["items"]]
    assert seqs == sorted(set(seqs))
    assert second["items"][0]["seq"] == first["to_seq"] + 1


def test_digest_cloud_safe_hides_local_only(conn):
    session(conn)
    ev(conn, 1, "user/message", "public", turn=1)
    ev(conn, 2, "user/message", "très privé", turn=2, privacy="local_only")
    texts = [i["text"] for i in L.digest(conn, SID, max_privacy="cloud_allowed")["items"]]
    assert "très privé" not in texts


def test_digest_native_id(conn):
    two_turns(conn)
    assert L.digest(conn, NATIVE, max_privacy="cloud_allowed")["session"]["session_id"] == SID


def test_digest_drops_injected_user_text(conn):
    session(conn)
    ev(conn, 1, "user/message", "# AGENTS.md instructions\n\n<INSTRUCTIONS>règles</INSTRUCTIONS>", turn=1)
    ev(conn, 2, "user/message", "Base directory for this skill: /x/skills/brainstorming\n\n# Brainstorming", turn=2)
    ev(conn, 3, "user/message", '<external_codex_apps_open_page>{"page_id":null}</external_codex_apps_open_page>', turn=3)
    ev(conn, 4, "user/message", "<environment_context>\n<cwd>/root</cwd>\n</environment_context>", turn=4)
    ev(conn, 5, "user/message", "Fais le tableau", turn=5)
    d = L.digest(conn, SID, max_privacy="cloud_allowed")
    assert [i["text"] for i in d["items"]] == ["Fais le tableau"]
    assert d["to_seq"] == 5


def test_digest_caps_one_item(conn):
    session(conn)
    ev(conn, 1, "user/message", "z" * 20000, turn=1)
    item = L.digest(conn, SID, max_privacy="cloud_allowed")["items"][0]
    assert len(item["text"]) < 7000
