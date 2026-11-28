"""Passive replay of persisted V1 Computer Use call/result pairs.

The reader opens Hermes state.db read-only and never imports a Computer Use
backend.  It advances its cursor only after a result has been correlated, so a
partially persisted call cannot disappear between polling cycles.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ShadowReplayEvent:
    session_id: str
    call_id: str
    action: str | None
    arguments: dict[str, Any]
    result: Any
    call_message_id: int
    result_message_id: int
    called_at: float
    completed_at: float


@dataclass(frozen=True)
class ShadowReplayBatch:
    events: tuple[ShadowReplayEvent, ...]
    next_cursor: int
    additional_backend_calls: int = 0
    errors: tuple[str, ...] = ()


class ShadowReplayReader:
    """Read completed ``computer_use`` calls without touching the live backend."""

    def __init__(self, database: str | Path, *, batch_size: int = 100) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.database = Path(database)
        self.batch_size = batch_size

    def read_after(self, cursor: int) -> ShadowReplayBatch:
        if cursor < 0:
            raise ValueError("cursor cannot be negative")
        connection = sqlite3.connect(
            f"file:{self.database}?mode=ro", uri=True
        )
        connection.row_factory = sqlite3.Row
        try:
            results = connection.execute(
                """
                SELECT id, session_id, content, tool_call_id, timestamp
                FROM messages
                WHERE id > ? AND role = 'tool' AND tool_name = 'computer_use'
                ORDER BY id
                LIMIT ?
                """,
                (cursor, self.batch_size),
            ).fetchall()
            events: list[ShadowReplayEvent] = []
            errors: list[str] = []
            next_cursor = cursor
            for result_row in results:
                call = self._find_call(connection, result_row)
                if call is None:
                    errors.append(
                        f"unpaired_result:{result_row['id']}:{result_row['tool_call_id']}"
                    )
                    break
                event = self._event(call, result_row)
                if event is None:
                    errors.append(
                        f"quarantined_invalid_pair:{result_row['id']}:{result_row['tool_call_id']}"
                    )
                    next_cursor = int(result_row["id"])
                    continue
                events.append(event)
                next_cursor = int(result_row["id"])
            return ShadowReplayBatch(
                events=tuple(events),
                next_cursor=next_cursor,
                additional_backend_calls=0,
                errors=tuple(errors),
            )
        finally:
            connection.close()

    @staticmethod
    def _find_call(
        connection: sqlite3.Connection, result_row: sqlite3.Row
    ) -> tuple[sqlite3.Row, dict[str, Any]] | None:
        rows = connection.execute(
            """
            SELECT id, session_id, tool_calls, timestamp
            FROM messages
            WHERE session_id = ? AND id < ? AND role = 'assistant'
              AND tool_calls IS NOT NULL
            ORDER BY id DESC
            """,
            (result_row["session_id"], result_row["id"]),
        )
        wanted = result_row["tool_call_id"]
        for row in rows:
            try:
                calls = json.loads(row["tool_calls"])
            except (TypeError, ValueError):
                continue
            if not isinstance(calls, list):
                continue
            for call in calls:
                if isinstance(call, dict) and call.get("id") == wanted:
                    return row, call
        return None

    @staticmethod
    def _event(
        pair: tuple[sqlite3.Row, dict[str, Any]], result_row: sqlite3.Row
    ) -> ShadowReplayEvent | None:
        call_row, call = pair
        function = call.get("function")
        if not isinstance(function, dict) or function.get("name") != "computer_use":
            return None
        try:
            arguments = json.loads(function.get("arguments") or "{}")
            result = json.loads(result_row["content"] or "null")
        except (TypeError, ValueError):
            return None
        if not isinstance(arguments, dict):
            return None
        action = arguments.get("action")
        return ShadowReplayEvent(
            session_id=str(result_row["session_id"]),
            call_id=str(result_row["tool_call_id"]),
            action=str(action) if action is not None else None,
            arguments=arguments,
            result=result,
            call_message_id=int(call_row["id"]),
            result_message_id=int(result_row["id"]),
            called_at=float(call_row["timestamp"]),
            completed_at=float(result_row["timestamp"]),
        )
