# Session Discovery Implementation Notes

## Problem

The original `skill_gap_detector.py` attempts to read session files from:
```
~/.hermes/sessions/session_*.json
```

But Hermes stores session data in a SQLite database, not flat JSON files. The actual path is:
```
~/.hermes/state/state.db
```

This means the gap detector script fails silently (returns empty results) on current Hermes installs.

## Correct Implementation

Use `sqlite3` to query the `sessions` table:

```python
import sqlite3
import json
from pathlib import Path

STATE_DB = Path.home() / ".hermes" / "state" / "state.db"

def discover_sessions(limit: int = 30):
    sessions = []
    with sqlite3.connect(STATE_DB) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT session_id, title, messages "
            "FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        for row in cursor.fetchall():
            session_id, title, messages_json = row
            messages = json.loads(messages_json) if messages_json else []
            sessions.append({
                "session_id": session_id,
                "title": title or "",
                "messages": messages,
            })
    return sessions
```

## Schema Reference (Hermes state.db)

Key table: `sessions`
- `session_id` (TEXT, PK)
- `title` (TEXT)
- `source` (TEXT) — e.g., "cron", "tui"
- `started_at` (REAL, unix timestamp)
- `last_active` (REAL, unix timestamp)
- `messages` (TEXT, JSON array of message objects)

## Pitfall

Do not fall back to filesystem globbing (`*.json`) without checking if state.db exists. The SQLite DB is the source of truth.