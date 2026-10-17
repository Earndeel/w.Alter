---
name: walter-logs-ingestion
description: Use when verifying or repairing the raw walter-logs journal across Hermes state.db, Codex, Claude Code and DSH, especially missing current conversation events or hourly-only ingestion.
---
# Verify raw log ingestion

walter-logs is the raw common journal of every Walter harness, including the main Hermes state.db and all profile databases. It is PostgreSQL schema walter_logs, not Hindsight derived memory or core.events. Hermes daily JSONL exports are an additional source copy. The full PG backup includes walter_logs.

1. Read /opt/walter-memory/walter_memory/logs.py and connectors/walter_logs.py before changing the collector. Check systemctl show walter-logs-watch and its recent journal. Service active alone does not prove live ingestion.
2. Verify the actual current conversation, not just a recently updated connector checkpoint. Use cloud-safe MCP logs_search for an exact recent user phrase. If diagnosing locally, query only event metadata by known session_id: type, seq, occurred_at, ingested_at. Do not print raw tool outputs, credentials, or local_only text into a cloud conversation.
3. Compare Hermes SQLite max message IDs with ingestion.checkpoints for connector walter_logs and streams hermes:<profile>. Open each SQLite source read-only. Check logs.hermes_dbs() for the main database and every profile. A current cursor proves tail freshness, not historical parser completeness.
4. If transcripts update locally but PG updates only hourly, inspect logs.ROOTS, Path.resolve() and logs.runtime_of(). Resolve both the source path and the configured root before containment checks. Respect path boundaries: sessions-other must not match sessions.
5. Preserve historical checkpoint identities across path aliases. sync_transcript uses logs.transcript_source_path() to map a real or alias path back under the configured logical root. Do not create a second cursor namespace or reset cursors as a shortcut.
6. Before edits, back up files under /root/.hermes/backups/<session>/. Add a regression using a real temporary directory and symlink, testing both paths and a sibling prefix. Run /opt/walter-memory/venv/bin/python -m pytest -q tests/test_logs.py from /opt/walter-memory.
7. Restart only walter-logs-watch after a verified fix. Its startup sweep catches up missed records idempotently. Then verify a new real tool call AND result written after catch-up, and measure ingestion lag. Avoid claiming completeness from service status or old events.
8. After changing a memory service, run systemctl start memory-autopilot and inspect the full report, including failed sub-operations; score 100 alone is insufficient. Document the cause, backup path and live evidence in DECISIONS.md. Commit only the files changed for the fix.

Known case, 2026-10-17: .codex was a symlink into .hermes/integrations/codex. Commit 8c2859d fixes root resolution and canonical checkpoint paths. Current user messages and tool calls/results were verified in PG with subsecond lag after restart.
