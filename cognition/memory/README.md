# walter-memory

| | |
|---|---|
| **Rôle** | Walter Memory : événements et objets canoniques, leur provenance, les connaissances dérivées, Kardex et l'index de recherche. Héberge aussi le bus Walter et walter-logs. |
| **Propriétaire** | walter-memory (`/walter/memory`). |
| **État** | **active** (constat du 09/11/2026) : `walter-memory-gateway` (:8890), `walter-logs-watch`, timers des connecteurs ; génération g0 active, g1 lue aussi. Nettoyage : phases 0 et 1 faites le 09/11/2026 ([docs/NETTOYAGE-2026-11.md](docs/NETTOYAGE-2026-11.md)). |
| **Ne fait pas** | Garder les octets bruts (Raw Vault, [vault/](vault/README.md)) ; choisir un modèle (Router) ; décider ce qui entre dans le contexte (Context). |
| **Contrats** | [contracts/memory.json](contracts/memory.json), [bus.json](contracts/bus.json), [logs.json](contracts/logs.json), [data-classes.json](contracts/data-classes.json), [maintenance.json](contracts/maintenance.json) ; [migrations/](migrations/) ; MCP `memory_*`, `logs_*`, `vault_*` ; passerelle 127.0.0.1:8890. |

Walter Memory core (spec and decisions: `/walter/docs/` — ARCHITECTURE, DECISIONS, PLAN, RUNBOOK).

- `migrations/` — SQL, applied in order by `walter-memory migrate` (each file recorded in `core.schema_migrations`).
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

- `walter_memory.overland` — restricted Overland GPS ingress, separate systemd unit on loopback :3010; see `docs/OVERLAND.md`. Raw samples stay local_only.
