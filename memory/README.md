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
