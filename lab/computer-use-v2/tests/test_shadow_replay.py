from __future__ import annotations

import json
import sqlite3

from adaptive_operator.shadow_replay import ShadowReplayReader


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


def _tool_call(call_id: str, *, action: str, extra: dict | None = None) -> str:
    arguments = {"action": action, **(extra or {})}
    return json.dumps(
        [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "computer_use",
                    "arguments": json.dumps(arguments),
                },
            }
        ]
    )


def test_replay_pairs_persisted_result_and_advances_by_result_message(tmp_path):
    db_path = tmp_path / "state.db"
    connection = _db(db_path)
    connection.execute(
        "INSERT INTO messages VALUES (1, 's1', 'assistant', '', NULL, ?, NULL, 10.0)",
        (_tool_call("call-1", action="capture", extra={"mode": "ax", "app": "Finder"}),),
    )
    connection.execute(
        "INSERT INTO messages VALUES (2, 's1', 'tool', ?, 'call-1', NULL, 'computer_use', 10.5)",
        (json.dumps({"mode": "ax", "app": "Finder", "elements": [], "total_elements": 0}),),
    )
    connection.commit()
    connection.close()

    batch = ShadowReplayReader(db_path).read_after(0)

    assert batch.next_cursor == 2
    assert batch.additional_backend_calls == 0
    assert len(batch.events) == 1
    event = batch.events[0]
    assert event.call_id == "call-1"
    assert event.action == "capture"
    assert event.arguments == {"action": "capture", "mode": "ax", "app": "Finder"}
    assert event.result["mode"] == "ax"
    assert event.call_message_id == 1
    assert event.result_message_id == 2
    assert event.session_id == "s1"

    assert ShadowReplayReader(db_path).read_after(batch.next_cursor).events == ()


def test_replay_does_not_advance_past_unpaired_tool_result(tmp_path):
    db_path = tmp_path / "state.db"
    connection = _db(db_path)
    connection.execute(
        "INSERT INTO messages VALUES (5, 's1', 'tool', '{}', 'late-call', NULL, 'computer_use', 20.0)"
    )
    connection.commit()
    connection.close()

    batch = ShadowReplayReader(db_path).read_after(0)

    assert batch.events == ()
    assert batch.next_cursor == 0
    assert batch.errors == ("unpaired_result:5:late-call",)


def test_replay_quarantines_malformed_completed_pair_and_continues(tmp_path):
    db_path = tmp_path / "state.db"
    connection = _db(db_path)
    connection.execute(
        "INSERT INTO messages VALUES (1, 's1', 'assistant', '', NULL, ?, NULL, 10.0)",
        (_tool_call("bad-call", action="capture"),),
    )
    connection.execute(
        "INSERT INTO messages VALUES (2, 's1', 'tool', 'not-json', 'bad-call', NULL, 'computer_use', 10.5)"
    )
    connection.execute(
        "INSERT INTO messages VALUES (3, 's1', 'assistant', '', NULL, ?, NULL, 11.0)",
        (_tool_call("good-call", action="list_apps"),),
    )
    connection.execute(
        "INSERT INTO messages VALUES (4, 's1', 'tool', '{}', 'good-call', NULL, 'computer_use', 11.5)"
    )
    connection.commit()
    connection.close()

    batch = ShadowReplayReader(db_path).read_after(0)

    assert [event.call_id for event in batch.events] == ["good-call"]
    assert batch.next_cursor == 4
    assert batch.errors == ("quarantined_invalid_pair:2:bad-call",)
