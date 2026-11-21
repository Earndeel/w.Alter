#!/usr/bin/env python3
"""Measure per-role payload composition from Hermes state.db.

Usage:
    python3 payload-composition-measurement.py [SESSION_ID]

If no SESSION_ID is given, shows the largest active session.
Reports role breakdown, top largest messages, and total chars/tokens.
"""

import sqlite3
import sys
import os


DB_PATH = os.path.expanduser("~/.hermes/state.db")


def measure(session_id: str):
    db = sqlite3.connect(DB_PATH)

    # Session info
    row = db.execute(
        """SELECT id, source, model, message_count, input_tokens, output_tokens,
                  cache_read_tokens, cache_write_tokens, estimated_cost_usd
           FROM sessions WHERE id = ?""",
        (session_id,),
    ).fetchone()
    if not row:
        print(f"Session {session_id} not found.")
        return

    sid, src, model, mc, it, ot, cr, cw, cost = row
    print(f"Session: {sid}")
    print(f"  source={src}, model={model}")
    print(f"  msgs={mc}, input_tokens={it}, output_tokens={ot}")
    print(f"  cache_read={cr}, cache_write={cw}, cost=${cost or 0:.4f}")
    print()

    # Role breakdown
    print("=== Role Breakdown (active, non-compacted) ===")
    total = 0
    rows = db.execute(
        """SELECT role, COUNT(*), SUM(LENGTH(content)),
                  CAST(AVG(LENGTH(content)) AS INTEGER)
           FROM messages
           WHERE session_id = ? AND active = 1 AND compacted = 0
           GROUP BY role
           ORDER BY SUM(LENGTH(content)) DESC""",
        (session_id,),
    ).fetchall()
    for role, cnt, chars, avg in rows:
        total += (chars or 0)
    for role, cnt, chars, avg in rows:
        pct = 100.0 * (chars or 0) / total if total else 0
        print(f"  {role:12s} | {cnt:4d} msgs | {chars or 0:10d} chars | "
              f"avg={avg or 0:6d} | {pct:5.1f}%")
    print(f"  {'TOTAL':12s} | {'':>4s} | {total:10d} chars | 100.0%")
    print()

    # Top-10 largest
    print("=== Top-10 Largest Messages ===")
    for mid, role, chars, preview in db.execute(
        """SELECT id, role, LENGTH(content),
                  SUBSTR(content, 1, 100)
           FROM messages
           WHERE session_id = ? AND active = 1 AND compacted = 0
           ORDER BY LENGTH(content) DESC
           LIMIT 10""",
        (session_id,),
    ):
        print(f"  [{mid:5d}] {role:12s} | {chars:7d} chars | {preview[:80].strip()}")

    db.close()


def largest_active():
    db = sqlite3.connect(DB_PATH)
    row = db.execute(
        """SELECT id FROM sessions
           WHERE ended_at IS NULL
           ORDER BY message_count DESC
           LIMIT 1""",
    ).fetchone()
    db.close()
    return row[0] if row else None


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else largest_active()
    if sid:
        measure(sid)
    else:
        print("No active sessions found.")
