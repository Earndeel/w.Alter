from __future__ import annotations

import json
import sqlite3

from adaptive_operator.shadow_spool import ShadowSpool
from adaptive_operator.shadow_spool_cli import exit_code_for


def _db(path):
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_call_id TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL NOT NULL
        )
        """
    )
    return connection


def _pair(connection):
    calls = json.dumps([
        {
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "computer_use",
                "arguments": json.dumps({"action": "list_apps"}),
            },
        }
    ])
    connection.execute(
        "INSERT INTO messages VALUES (1, 's', 'assistant', '', NULL, ?, NULL, 1.0)",
        (calls,),
    )
    connection.execute(
        "INSERT INTO messages VALUES (2, 's', 'tool', ?, 'call-1', NULL, 'computer_use', 2.0)",
        (json.dumps({"apps": []}),),
    )


def test_spool_persists_records_and_cursor_idempotently(tmp_path):
    database = tmp_path / "state.db"
    connection = _db(database)
    _pair(connection)
    connection.commit()
    connection.close()
    spool = ShadowSpool(
        database=database,
        device_id="mac",
        output_dir=tmp_path / "spool",
    )

    first = spool.poll_once()
    second = spool.poll_once()

    assert first.records_seen == 1
    assert first.records_created == 1
    assert first.next_cursor == 2
    assert second.records_seen == 0
    assert second.records_created == 0
    assert second.next_cursor == 2
    assert first.additional_backend_calls == 0
    assert first.failures_affecting_v1 == 0
    event = json.loads((tmp_path / "spool" / "events" / "000000000002.json").read_text())
    assert event["call_id"] == "call-1"
    assert event["schema_version"] == "2.1"
    assert event["v1_persisted_interval_ms"] == 1000.0
    assert "v1_latency_ms" not in event
    assert event["policy"]["predicted_level"] == "L0"
    assert json.loads((tmp_path / "spool" / "cursor.json").read_text())["cursor"] == 2
    assert oct((tmp_path / "spool").stat().st_mode & 0o777) == "0o700"
    assert oct((tmp_path / "spool" / "events" / "000000000002.json").stat().st_mode & 0o777) == "0o600"


def test_spool_replay_does_not_overwrite_existing_event(tmp_path):
    database = tmp_path / "state.db"
    connection = _db(database)
    _pair(connection)
    connection.commit()
    connection.close()
    output = tmp_path / "spool"
    events = output / "events"
    events.mkdir(parents=True)
    existing = events / "000000000002.json"
    existing.write_text('{"sentinel":true}\n')
    spool = ShadowSpool(database=database, device_id="mac", output_dir=output)

    result = spool.poll_once(cursor=0)

    assert result.records_seen == 1
    assert result.records_created == 0
    assert existing.read_text() == '{"sentinel":true}\n'
    assert oct(existing.stat().st_mode & 0o777) == "0o600"
    assert result.next_cursor == 2


def test_cli_fails_on_blocking_replay_error_but_not_quarantine():
    class Result:
        replay_errors = ("unpaired_result:5:late-call",)

    assert exit_code_for(Result()) == 2

    Result.replay_errors = ("quarantined_invalid_pair:2:bad-call",)
    assert exit_code_for(Result()) == 0
