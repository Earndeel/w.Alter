---
name: walter-logs-idempotence-repair
description: Use when walter-logs contains duplicate events after transcript rewrites, session resumes, checkpoint resets, or Hermes message re-persistence.
---

## Diagnose event identity before removing copies

- Read Walter Memory's ARCHITECTURE.md and DECISIONS.md before changing ingestion or stored history.
- Resolve the module with `cd "$(walter path memory)"` and inspect `walter_memory/logs.py`, `connectors/walter_logs.py`, and migrations 015 and 016. Check current CLI behavior before running repair commands.
- Treat `(session_id, type, occurred_at, text)` matches as duplicate candidates, not proof. Inspect `data`, native event identifiers, and original source records: distinct tool events or model selections can share timestamps and text.
- Do not use transcript byte offsets or Hermes SQLite row IDs as durable event identity. Claude Code can re-append the same native event; transcript rewrites shift offsets; Hermes can persist the same message under another row ID.
- Use the implemented `event_key()` rules consistently for ingestion, historical backfill, and quarantine. Preserve legitimate repeated events and leave existing sequence numbers stable.
- Inspect Hermes SQLite through Python's `sqlite3` with `sqlite3.connect('file:PATH?mode=ro', uri=True)` if the `sqlite3` executable is unavailable. Never modify the source databases.

## Back up and backfill keys

1. Create a protected, dated backup directory under `/root/.hermes/backups/`. Back up modified code and decision records as well as the database schema.
2. Export the schema with `docker exec hindsight-pg pg_dump -U hindsight -d hindsight -n walter_logs -Fc > "$backup_dir/walter_logs-before-keys.dump"`. Set `umask 077` before creating the file and verify successful completion.
3. Validate the archive with `docker exec -i hindsight-pg pg_restore -l < "$backup_dir/walter_logs-before-keys.dump"`. Check disk space before large backfills.
4. Confirm migrations 015 and 016 are applied through the project's migration procedure; do not blindly rerun migration SQL.
5. Stop the writer with `systemctl stop walter-logs-watch` before historical key backfill. Arrange to restart it if the repair fails.
6. Run a representative session first: `PGPASSFILE=/root/.pgpass walter-python connectors/walter_logs.py keys --session "$session_id"`.
7. Run the full backfill: `PGPASSFILE=/root/.pgpass walter-python connectors/walter_logs.py keys`.

## Quarantine confirmed copies

- Run `PGPASSFILE=/root/.pgpass walter-python connectors/walter_logs.py dedup` first; this is the dry run. Inspect the candidate count and any references from `views.member` before applying.
- Use the connector's quarantine operation rather than ad hoc deletion: `PGPASSFILE=/root/.pgpass walter-python connectors/walter_logs.py dedup --apply`.
- The October 2026 implementation uses null event keys for later historical copies after backfill. Verify that implementation before interpreting a null key as a duplicate; null alone is not a general duplicate criterion.
- Verify the quarantine retains the original event and identifies its surviving canonical sequence. Check that no view membership points to a quarantined copy.
- Restart ingestion with `systemctl start walter-logs-watch`, then check `systemctl is-active walter-logs-watch` and `journalctl -u walter-logs-watch --since '-5min' --no-pager`.

## Verify replay safety and memory health

- Run `walter-python -m pytest -q tests/test_logs_idempotence.py tests/test_logs.py tests/test_views.py`.
- Verify replay from the beginning, shifted transcript offsets, repeated native events, and Hermes messages persisted under new row IDs. Exact replays must add zero copies; legitimate repeated events must remain distinct. Use rolled-back database tests or isolated fixtures, not live checkpoint edits.
- Recheck active event counts, quarantine counts, missing keys, and view references after ingestion resumes.
- Run `walter-memory health` and `systemctl start memory-autopilot`. Wait for a fresh `/root/.hermes/logs/memory-autopilot/latest.json` and inspect its `summary`; do not assume the score is a top-level field.
- Record the identity rules, quarantine outcome, validation results, and commits in DECISIONS.md. Never renumber surviving events or erase quarantined evidence as routine cleanup.
