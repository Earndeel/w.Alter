from __future__ import annotations

import json
import sqlite3

from adaptive_operator.observation import ObservationDetail
from adaptive_operator.shadow_sidecar import ShadowSidecar


def _database(path):
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


def _insert_pair(connection, base_id, call_id, action, result, arguments=None):
    payload = {"action": action, **(arguments or {})}
    calls = json.dumps([
        {
            "id": call_id,
            "type": "function",
            "function": {
                "name": "computer_use",
                "arguments": json.dumps(payload),
            },
        }
    ])
    connection.execute(
        "INSERT INTO messages VALUES (?, 's', 'assistant', '', NULL, ?, NULL, ?)",
        (base_id, calls, float(base_id)),
    )
    connection.execute(
        "INSERT INTO messages VALUES (?, 's', 'tool', ?, ?, NULL, 'computer_use', ?)",
        (base_id + 1, json.dumps(result), call_id, float(base_id + 1)),
    )


def test_sidecar_observes_existing_payloads_without_backend_calls(tmp_path):
    database = tmp_path / "state.db"
    connection = _database(database)
    _insert_pair(
        connection,
        1,
        "capture-1",
        "capture",
        {"app": "Example", "elements": [{"role": "button", "label": "Open"}]},
        {"mode": "ax"},
    )
    _insert_pair(connection, 3, "launch-1", "launch_app", {}, {"name": "Example"})
    connection.commit()
    connection.close()

    result = ShadowSidecar(
        database=database,
        device_id="mac",
        detail=ObservationDetail.RELEVANT,
    ).poll_once(cursor=0)

    assert result.next_cursor == 4
    assert result.additional_backend_calls == 0
    assert result.failures_affecting_v1 == 0
    assert len(result.records) == 2
    capture, launch = result.records
    assert capture.observation is not None
    assert capture.observation["snapshot"] == "s:2"
    assert capture.compaction["additional_backend_calls"] == 0
    assert launch.policy["predicted_level"] == "L1"
    assert launch.policy["would_warn"] is True


def test_sidecar_contains_conversion_error_and_continues(tmp_path):
    database = tmp_path / "state.db"
    connection = _database(database)
    _insert_pair(connection, 1, "bad-capture", "capture", {"elements": "not-a-list"})
    _insert_pair(connection, 3, "read-1", "list_apps", {"apps": []})
    connection.commit()
    connection.close()

    result = ShadowSidecar(database=database, device_id="mac").poll_once(cursor=0)

    assert result.next_cursor == 4
    assert len(result.records) == 2
    assert result.records[0].shadow_error is None
    assert result.records[1].policy["predicted_level"] == "L0"
    assert result.failures_affecting_v1 == 0
