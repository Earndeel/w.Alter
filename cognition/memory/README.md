# walter-memory

Walter Memory core (spec and decisions: `/root/.hermes/docs/walter-memory/`).

- `migrations/` — SQL, applied in order (`docker exec -i hindsight-pg psql -U hindsight -d hindsight < file`).
- `event_types/v1.json` — seed of the extensible taxonomy (`walter-memory types sync`).
- `walter_memory/` — library: `events` (append-only canonical store), `objects` (single Raw Vault registry,
  clear/secure zones), `privacy` (classes, detectors, redaction), `llm` (the only door to external models:
  privacy + budget guard + accounting), `ingestion` (connectors, checkpoints, SKIP LOCKED queue), `purge`
  (break-glass), `gateway` (HTTP 127.0.0.1:8890), `cli` (`walter-memory`).
- `connectors/` — source connectors (P2).
- `tests/` — `venv/bin/python -m pytest -q tests/`.

- `ops/` — authoritative offsite backup/restore and maintenance scripts; installed entrypoints are symlinks.
- `walter_memory.backup_bundle` — discover module sources and integration dependencies; consistent profile SQLite
  snapshots; versioned SHA-256/mode/link manifest, Python package inventories and mandatory entrypoint checks.
  PG (all schemas), main Hermes SQLite and existing Raw Vault objects are separate payloads. Verification does
  not yet prove a complete install on a clean VM. See the operational runbook for encrypted restore commands.
- `walter_memory.hygiene` — bounded, reversible PostgreSQL/Hindsight quarantine; dry-run by default, snapshots
  before `--apply`. Canonical events and raw agent logs are never deleted by this maintenance.

- `walter_memory.overland` — restricted Overland GPS ingress, separate systemd unit on loopback :3010; see `docs/OVERLAND.md`. Raw samples stay local_only.
