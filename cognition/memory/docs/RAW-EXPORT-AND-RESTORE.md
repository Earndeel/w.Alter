# Raw exports, runtime logs and isolated reconstruction

Verified 2026-10-18. These are three separate contracts.

- `walter_logs` is the normalized append-only journal of what runtimes expose. Hermes main and profiles, Codex, Claude Code and DSH are collected incrementally. Secrets are masked before insertion; wild is local_only. PostgreSQL backups include this journal and its cursors. Hidden encrypted reasoning is represented as encrypted metadata, not reconstructed text.
- `state.db` belongs to Hermes. Main is backed up daily without rebuildable FTS indexes; every profile database is copied consistently in the offsite config bundle. These snapshots preserve native tables that normalized logs do not reproduce.
- `walter_memory.hermes_export` implements A1/D1: complete past UTC days of sessions/messages, all SQLite columns, JSONL.zst, always local_only in the secure Raw Vault. Each profile has its own cursor. No harness package, model, or provider API is used.

## Raw export operation

`walter-memory-hermes-export.timer` runs daily at 02:10 UTC, persistent. The service invokes:

```
/opt/walter-memory/venv/bin/python /opt/walter-memory/connectors/hermes.py \
  --export-only --all-profiles --export-days 31 --export-seconds 900
```

SQLite is forced read-only even for bare paths or a supplied rw URI. One row is compressed at a time in a private temporary directory. Dates are checked; invalid timestamps fail instead of silently advancing. Current UTC day is excluded. A directory named `profiles/main` is distinct from the default profile through explicit default_profile metadata and a different connector key.

A per-profile advisory lock serializes exporters. The archive upload/HEAD check precedes a single PG transaction committing catalogue plus daily checkpoint. A crash before that commit can leave an orphan uploaded object; deterministic content/hash deduplication reuses identical bytes on retry. Existing catalogue entries for that logical day are verified and reused. A 31-day limit or timeout leaves remaining work explicit; rerunning resumes. SQLite scans have a progress deadline; S3 uses 10s connect/30s read timeouts and at most two retries. The systemd outer timeout is three hours. Reports contain counts only; errors omit exception values.

Completed archives are immutable. Late edits to an old source timestamp do not rewrite that day; normalized logs and current SQLite snapshots are the complementary recovery paths. The exporter does not archive unrelated SQLite tables; snapshots do. A successful S3 HEAD can refer to the local write-back cache. Offsite qualification therefore also checks sizes on `rawvault-secure:` and decrypts a representative object in memory to verify SHA256, without printing contents.

Checkpoints: `ingestion.checkpoints`, stream `export`, connector `hermes` for default, `hermes:<name>` for profiles. Export health has its own `hermes_raw_export` connector, so an archive success does not falsely refresh canonical ingestion health.

## Bundle contract

`backup_bundle.create` validates owner contracts against the generated registry before opening an output archive and again before finalizing it. It fails on schema, ownership, dependency, missing source, or registry drift. Archives predating the contract catalogue retain v1 compatibility. Source files, integrations, symlinks, permissions, SQLite profile snapshots and environment package inventories are checksummed; generated environments/model weights are excluded.

## Isolated reconstruction command

```
PYTHONPATH=/opt/walter-memory /opt/walter-memory/venv/bin/python \
  -m walter_memory.restore_drill \
  --report /root/.hermes/logs/walter-restore-isolated/latest.json
```

Run the command as a systemd oneshot for a sustained rehearsal. It downloads the latest PG/state/config age backups, decrypts only into a private scratch directory, verifies the archive manifest, reconstructs a separate filesystem, rebases absolute symlinks within that root, checks contracts and SQLite, and parses restored Python sources without executing them.

PostgreSQL is rebuilt from the locally available production image in a new disposable container: no network, no ports, read-only container root, one CPU, four GiB memory, only its scratch data mounted. No restored service, timer, consumer, message sender, model or Mac action is started. Database/config scratch and the container are removed after the report. Free scratch space must exceed twice the live PG size plus 4 GiB (minimum 12 GiB); no cloud infrastructure is created.

This proves database and file reconstruction in isolation. It does not prove clean VM boot, full Python environment rebuild, complete module service startup, all external integrations, or possession of the recovery key after loss of this VM. RPO/RTO targets remain an owner decision. Raw Vault object bytes are on Drive, not a second independent copy; access recovery and an independent media backup policy remain separate contracts.
