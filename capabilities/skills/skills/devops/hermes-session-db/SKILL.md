---
name: hermes-session-db
description: "Hermes Agent SQLite session database (state.db) — schema, contents, query patterns, and relationship to other memory layers (Hindsight PG, Qdrant). Verified by direct inspection."
triggers:
  - Need to query or understand Hermes session history storage
  - Debugging session_search / FTS5 recall
  - Auditing what conversation data persists across turns
  - Correlating session DB with Hindsight memory layers
---

# Hermes Session Database (SQLite)

## Overview

**File**: `~/.hermes/state.db` (≈1.2 GB as of 2026-06-15)
**Engine**: SQLite 3 with FTS5 (full-text search)
**Purpose**: Persistent conversation history for `session_search` tool — stores every turn with full fidelity.

## Schema (verified 2026-06-15)

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,                    -- 'user' | 'assistant' | 'tool'
    content TEXT,                          -- final assistant response / user message / tool output
    tool_call_id TEXT,                     -- correlation ID for tool call → result pairing
    tool_calls TEXT,                       -- JSON array of tool calls (assistant messages only)
    tool_name TEXT,                        -- tool name for role='tool' messages
    timestamp REAL NOT NULL,               -- Unix epoch
    token_count INTEGER,
    finish_reason TEXT,                    -- 'stop' | 'tool_calls' | etc.
    reasoning TEXT,                        -- FULL reasoning/thinking block (can be 200+ chars)
    reasoning_details TEXT,
    codex_reasoning_items TEXT,
    reasoning_content TEXT,
    codex_message_items TEXT,
    platform_message_id TEXT,
    observed INTEGER DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);

-- FTS5 virtual table for full-text search (session_search)
CREATE VIRTUAL TABLE messages_fts USING fts5(...);
-- Trigram variant for fuzzy matching
CREATE VIRTUAL TABLE messages_fts_trigram USING fts5(...);
```

## What IS Stored (verified by direct query)

| Data | Column | Example |
|------|--------|---------|
| User messages | `role='user'`, `content` | Raw user text |
| Assistant final response | `role='assistant'`, `content` | Final answer text |
| **Tool calls (full JSON)** | `tool_calls` (assistant row) | `[{"id": "...", "function": {"name": "terminal", "arguments": "..."}}]` |
| **Tool results (raw output)** | `role='tool'`, `content` | Complete stdout/stderr/error |
| **Reasoning/thinking blocks** | `reasoning` (assistant row) | Full internal monologue, 200+ chars |
| Tool call correlation | `tool_call_id` + `tool_name` | Links assistant→tool rows |

**Critical correction**: Prior memory claimed *"Raw tool call results and thinking blocks are not stored in state.db to conserve disk space."* — **THIS IS FALSE**. Direct inspection (2026-06-15) confirms all three are persisted.

## What is NOT Stored

- Model logits / hidden states / attention weights
- Provider-level metadata (latency, token breakdowns per provider)
- Ephemeral in-turn state (cache, partial streams)

## Query Patterns

### Direct SQL (python3)
```python
import sqlite3
conn = sqlite3.connect('/root/.hermes/state.db')
conn.row_factory = sqlite3.Row
# Recent tool calls with reasoning
cursor.execute("""
    SELECT id, role, tool_calls, tool_name, substr(reasoning,1,200) as r
    FROM messages
    WHERE tool_calls IS NOT NULL OR reasoning IS NOT NULL
    ORDER BY id DESC LIMIT 10
""")
```

### Via `session_search` tool (FTS5)
- `session_search(query="terminal aws bedrock", limit=5)` — finds turns by content
- `session_search(session_id="...", around_message_id=12345, window=10)` — scroll context

## Relationship to Other Memory Layers

```
┌─────────────────────────────────────────────────────────────┐
│  SESSION DB (SQLite, ~/.hermes/state.db)                    │
│  • Complete conversation history (all turns, full fidelity) │
│  • FTS5 search → session_search tool                        │
│  • Retention: indefinite (manual cleanup only)              │
└─────────────────────────┬───────────────────────────────────┘
                          │ on_pre_compress / /remember / [SAVE]
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  HINDSIGHT PG (PostgreSQL, hindsight-pg:5432)               │
│  • Truth store: memory_facts, memory_units, entities        │
│  • Extracted durable facts (not raw conversation)           │
│  • Powers: hindsight_recall tool, dream cycle, user model   │
└─────────────────────────┬───────────────────────────────────┘
                          │ async outbox + pg_qdrant_sync_worker
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  QDRANT (vector DB, port 6333)                              │
│  • Fast semantic index (768-dim Gemini Embed 2)             │
│  • Hybrid search (port 8889) + Memory Sniper injection      │
│  • Active recall index (subset of PG, kept fresh)           │
└─────────────────────────────────────────────────────────────┘
```

**Key distinction**: Session DB = **verbatim conversation history**. Hindsight PG = **extracted durable knowledge**. Qdrant = **semantic search index over extracted knowledge**.

## Pitfalls

1. **Don't confuse layers** — `session_search` queries SQLite (FTS5). `hindsight_recall` queries PG (port 8888) or Hybrid Search (port 8889). Different coverage, different scoring.

2. **Disk growth** — `state.db` grows unbounded. No automatic rotation. Monitor size; consider periodic vacuum/archive if >5 GB.

3. **Tool result pairing** — Tool calls (assistant row, `tool_calls` JSON) and results (tool row, `content`) are separate rows linked by `tool_call_id`. Join on that for full call→result trace.

4. **Reasoning column** — Can be large (multi-paragraph). `session_search` FTS5 indexes it, so reasoning content is searchable.

## Estimating Token Volume Across Hermes DBs

When Monsieur asks "combien de tokens dans la DB Hermes", do **not** stop at the active `~/.hermes/state.db` message table unless he explicitly says session history only. Hermes deployments can have several DB layers:

1. **Active session SQLite**: `~/.hermes/state.db` — canonical raw session history.
2. **Profile session DBs**: `~/.hermes/profiles/*/state.db` — usually much smaller but still separate history branches.
3. **State snapshots/backups**: `~/.hermes/state-snapshots/*/state.db` — physical storage duplicates, not active memory.
4. **Hindsight PostgreSQL**: usually Docker `hindsight-pg`, database `hindsight` — extracted memory/facts/user-model/Kardex, separate from session DB.
5. **Qdrant**: vector index payloads for Hindsight — mostly mirrors active memory facts; count separately only when estimating physical stored text, not logical unique memory.
6. **Auxiliary SQLite DBs**: Kanban, OpenClaw/OpenCode/Codex integrations, browser profile DBs, custom research DBs.

Use two totals because they answer different questions:
- **Logical text tokens**: count raw meaningful text tables (`messages.content`, `tool_calls`, reasoning columns, PG text/json fields) and avoid counting FTS/index mirrors and backups unless requested.
- **Physical stored text tokens**: include SQLite FTS virtual tables, snapshots, and mirrored vector payload text. This number can be several times larger because FTS duplicates session text.

Practical approximation: sum text characters, then report a range using `chars / 4` to `chars / 3.5`. Label it as approximate unless `tiktoken` or the target provider tokenizer was actually run. Be explicit whether the result includes FTS tables, snapshots, PG/Hindsight, and Qdrant payloads — otherwise the number is technically correct and practically misleading, the worst dressed kind of correct.

## Verification Commands

```bash
# Schema
python3 -c "import sqlite3; c=sqlite3.connect('/root/.hermes/state.db'); print([r[0] for r in c.execute(\"SELECT sql FROM sqlite_master WHERE type='table'\")])"

# Count rows
python3 -c "import sqlite3; c=sqlite3.connect('/root/.hermes/state.db'); print(c.execute('SELECT COUNT(*) FROM messages').fetchone()[0])"

# Sample tool call + reasoning
python3 -c "
import sqlite3, json
c=sqlite3.connect('/root/.hermes/state.db')
for r in c.execute('SELECT id,role,tool_calls,tool_name,reasoning FROM messages WHERE tool_calls IS NOT NULL OR role=\"tool\" ORDER BY id DESC LIMIT 3'):
    print(f'ID={r[0]} role={r[1]} tool_calls={r[2] is not None} tool_name={r[3]} reasoning_len={len(r[4]) if r[4] else 0}')
"
```

## References

- `references/sqlite-session-db-verification-2026-06-15.md` — Direct inspection transcript proving tool_calls, tool results, and reasoning persistence