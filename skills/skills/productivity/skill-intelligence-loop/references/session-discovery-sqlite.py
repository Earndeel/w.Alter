#!/usr/bin/env python3
"""Skill Gap Detector — analyzes recent sessions to find patterns without skill coverage.

Scans recent session transcripts for:
1. Recurring tool call sequences (same tools used together 3+ times)
2. Long tool chains (5+ tool calls on same topic with no skill loaded)
3. Repeated error→fix patterns (agent fixed same issue multiple times)
4. Frequently referenced external services without dedicated skills

Usage:
    python3 skill_gap_detector.py [--sessions N] [--output DIR] [--json]
"""

import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
SKILLS_DIR = HERMES_HOME / "skills"
AUDIT_DIR = HERMES_HOME / "skill-audit"
STATE_DB = HERMES_HOME / "state" / "state.db"


# ---------------------------------------------------------------------------
# Session discovery (SQLite)
# ---------------------------------------------------------------------------

def discover_sessions(limit: int = 30) -> list[dict]:
    """Find recent sessions from the Hermes SQLite state database."""
    sessions = []
    if not STATE_DB.exists():
        return sessions

    try:
        conn = sqlite3.connect(STATE_DB)
        cursor = conn.cursor()
        # Try the sessions table schema
        cursor.execute(
            "SELECT session_id, title, started_at, last_active, messages "
            "FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()

        for row in rows:
            session_id, title, started_at, last_active, messages_json = row
            try:
                messages = json.loads(messages_json) if messages_json else []
            except (json.JSONDecodeError, TypeError):
                messages = []

            sessions.append({
                "session_id": session_id,
                "title": title or "",
                "messages": messages,
                "started_at": started_at,
            })
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to read state.db: {e}", file=sys.stderr)

    return sessions


# Ahead-of-time (AOT) #