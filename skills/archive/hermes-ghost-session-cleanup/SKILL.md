---
name: hermes-ghost-session-cleanup
category: devops
description: Fix and prevent accumulating ghost/orphan sessions in Hermes state.db by embedding auto-cleanup directly in the SessionDB.create_session() method -- the single entry point for all sessions (CLI, Telegram, gateway).
---

# Hermes Ghost Session Cleanup

## Problem
Hermes creates session entries in `state.db` that are never closed with `ended_at`, even when they contain zero messages. This happens when the CLI/Gateway crashes, is killed, or a session is initiated but never used. Over time: hundreds of phantom sessions accumulate.

## Root Cause
Sessions are created via `SessionDB.create_session()` before any messages are written. If the process dies before `end_session()` is called, the session stays `ended_at IS NULL` forever. Signal handlers and `atexit` exist but don't catch all crash scenarios.

## Solution: Self-Healing Cleanup in create_session()

Instead of external scripts, cron jobs, or startup hooks, the cleanup happens at the **single entry point** for ALL sessions -- `hermes_state.py`, method `create_session()`.

### Step 1: Add the cleanup method to SessionDB class

In `/root/.hermes/hermes-agent/hermes_state.py`, after `create_session()` and before `end_session()`:

```python
def _cleanup_ghost_sessions(self, max_age_seconds: int = 3600) -> int:
    """Close sessions that have no messages and are older than max_age_seconds.

    Called automatically by create_session() to prevent accumulating
    phantom/orphan session entries. Sessions with messages are NEVER
    touched — only true ghosts (created but never used).
    """
    def _do(conn):
        cutoff = time.time() - max_age_seconds
        cursor = conn.execute(
            "DELETE FROM sessions WHERE ended_at IS NULL "
            "AND started_at < ? "
            "AND id NOT IN (SELECT DISTINCT session_id FROM messages)",
            (cutoff,),
        )
        conn.commit()
        return cursor.rowcount
    cleaned = self._execute_write(_do)
    if cleaned > 0:
        import logging
        logging.getLogger(__name__).debug(
            "Cleaned up %d ghost sessions", cleaned
        )
    return cleaned
```

### Step 2: Call it in create_session()

Add `self._cleanup_ghost_sessions()` at the top of `create_session()`:

```python
def create_session(self, session_id, source, model=None, ...):
    """Create a new session record. Automatically cleans up ghost
    sessions (no messages, never resumed) to keep the DB tidy."""
    self._cleanup_ghost_sessions()  # <-- Add this line
    def _do(conn):
        conn.execute("INSERT OR IGNORE INTO sessions ...")
    self._execute_write(_do)
    return session_id
```

### Step 3: Restart Gateway

```bash
# Kill and restart gateway to load new code
pkill -f 'hermes gateway run'
cd /root/.hermes && nohup hermes gateway run --replace > /tmp/hermes_gateway.log 2>&1 &
```

### Step 4: One-time manual cleanup of existing ghosts

```python
import sqlite3
conn = sqlite3.connect('/root/.hermes/state.db')
# Delete ghosts (no messages, open)
conn.execute("DELETE FROM sessions WHERE ended_at IS NULL AND id NOT IN (SELECT DISTINCT session_id FROM messages)")
# Mark stale sessions (open, with messages, but older than threshold)
import time
conn.execute("UPDATE sessions SET ended_at=?, end_reason='stale_cleanup' WHERE ended_at IS NULL AND started_at < ?", (time.time(), time.time() - 86400))
conn.commit()
conn.close()
```

## Why This Design

**Not cron/external script**: Self-contained in the core library. No maintenance, no scheduling.

**Not startup hook**: `create_session()` is called by CLI, gateway, Telegram, and ALL sources. One injection point covers everything.

**Not signal-handler fix**: Signal handlers can't catch SIGKILL or segfaults. Cleanup at creation time catches the fallout regardless of how previous sessions died.

**Safe deletion criteria**:
- `ended_at IS NULL` — only unclosed sessions
- `started_at < cutoff` — gives a grace period (default 1h)
- `NOT IN (SELECT DISTINCT session_id FROM messages)` — NEVER touches sessions with actual content

## Additional: Fix Approval Bypassing

If `approvals.mode: yolo` still prompts for approval, check for `command_allowlist` in `/root/.hermes/config.yaml`. A non-empty allowlist can override yolo mode:

```yaml
# WRONG - causes approval prompts even in yolo
command_allowlist:
  - script execution via -e/-c flag

# CORRECT - no restrictions
command_allowlist: []
```

## Pitfalls

- Don't set `max_age_seconds` too low — long-running conversations could be mistaken for ghosts
- Don't use `ended_at IS NULL` alone as the criterion — actively open sessions would get deleted
- The `_execute_write` helper already handles WAL lock contention with jitter retries
- After patching, the gateway MUST restart to load the modified `hermes_state.py`
