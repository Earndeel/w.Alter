---
name: hermes-memory-ops
category: devops
description: "Use when diagnosing or maintaining Walter Memory (core.events, Raw Vault registry, Kardex, search index, connectors), walter-logs, memory backups, synthesis privacy or memory supervision."
tags: [memory, walter-memory, walter-logs, postgresql, pgvector, backups, maintenance, watchdog]
created: 2026-06-07
---

# Walter Memory operations

Current procedure, checked on the VM on 2026-11-01 (retirements updated 2026-11-09). The June–October Hindsight / Qdrant / write-worker / Jarvis
material is kept verbatim in `references/historical-2026-08-architecture.md` for provenance only.

## What is live (and what is not)

- **Durable truth** = `core.events` (append-only, idempotent, privacy-classed) + `core.objects` (Raw Vault registry)
  in Postgres `hindsight-pg` (127.0.0.1:5433, db `hindsight`; the container keeps its historical name; password
  only in `/root/.pgpass`, never printed). Kardex = schema `kardex` of the same database, fed only by walter-memory
  processors. Search = `search.chunks` (FTS + local embeddings, pgvector).
- **Code**: `/walter/memory` (link `/opt/walter-memory`), lib `walter_memory`, CLI `walter-memory`
  (`health`, `search`, `context`, `events`, `objects`, `social`, `logs`, `extract`, `purge`…).
- **Writes** only through the lib or `walter-memory-gateway` (127.0.0.1:8890). Never patch the upstream Hermes
  checkout; Hermes and its profiles use the memory provider `walter-memory`.
- **Connectors** = systemd timers `walter-memory-*` (hermes, hermes-export, beeper, gmail, calendar, index, social,
  extract, triage, agent-calls). Claude Code / Codex / DSH sessions arrive through the runtime hooks.
- **walter-logs** (what the agents did, every runtime, including Hermes state.db/profiles and Codex) = schema
  `walter_logs`, fed within seconds by `walter-logs-watch`. `core.events` is Monsieur's life; `walter_logs` is the
  agents' work. Do not mistake raw Vault exports for a walter_logs backup: the PG dumps contain both.
- **Retired — never restart or reinstall**: Hindsight API (:8888, retired 2026-10-19), Qdrant, hybrid-search,
  write-worker / write-bridge, pg-qdrant-sync, dream-cycle, Jarvis (2026-10-01), the ephemeral sweeper and
  kardex-hindsight-sync timers (2026-10-19); the Hermes cron jobs « Memory Health Check », « Memory Dreaming » and
  « Memory Importance Decay » (removed 2026-11-09; the Walter Guardians cover their useful checks). Do not install
  Qdrant clients to satisfy an old smoke test. **Hindsight's tables are gone** (Memory cleanup phase 1, 2026-11-09):
  the Hindsight objects of `public`, schemas `walter_voice` and `walter_audit`, the sync tables of `legacy`. Schema
  `public` now holds only the extensions (vector, pg_trgm, pgcrypto, unaccent): never `DROP SCHEMA public`. Their
  content stays in the encrypted dumps of `@instance/backups/memory-archive/` and
  `@instance/backups/changes/2026-11-09-memory-phase1/`; Hindsight's memories live on in `core.derived_items`
  (`derived_by = 'hindsight'`, generation g0).
- **Docs**: `/walter/docs/{ARCHITECTURE,DECISIONS,RUNBOOK,PLAN}.md` (moved from `~/.hermes/docs/walter-memory`
  on 2026-10-31; the old path is a link).

## Diagnose

1. `walter-memory health` (`/usr/local/bin/walter-memory`) — connector freshness, failures, queues, budgets, index
   lag. A `problems` list names what to look at (example 2026-11-01: `queue beeper_media: 3 dead jobs`).
2. `systemctl status walter-memory-gateway walter-logs-watch` and `systemctl list-timers 'walter-memory-*'`.
3. PG: `docker exec -i hindsight-pg psql -U hindsight -d hindsight …` (no password on the command line, never
   print secrets).
4. Hermes gateway is a **user** unit: `systemctl --user status hermes-gateway`, not the system service.
5. Raw journal coverage, checkpoints or duplicates: `walter-memory logs stats|sessions|search`; duplicate events after
   transcript rewrites → skill `walter-logs-idempotence-repair`.

## Maintain

- Recall noise: never delete canonical events or raw logs to clean recall (the old `walter_memory.hygiene` quarantine
  of Hindsight rows was removed with those tables on 2026-11-09).
- Real deletion only with `walter-memory purge` (break-glass, dry-run unless `--execute`, rewrites backups).
- Privacy classes can only be tightened (`walter-memory privacy-rescan`). L3 synthesis must exclude `local_only`
  before the call, carry the strictest included source class through `walter_memory.llm` into the derived item and
  its search chunk, and omit private titles. `privacy.tighten_derived_sources` defaults to dry-run: apply only after
  a metadata backup, tightening derived/chunk classes.
- External models only through `walter_memory.llm` (it refuses `local_only`, redacts `redacted_cloud`, enforces
  budgets); the model for each task comes from Walter Router, never hardcoded.
- After any memory repair: `systemctl start memory-autopilot`, then read
  `/root/.hermes/logs/memory-autopilot/latest.json`. The score includes walter-memory health and cleanup failures
  (warning score90 on 2026-10-17 was real: Beeper failed media, low provider balance); a score alone is not proof of
  business health.

## Backups and restore

`walter-pg-backup` (03:30 UTC, `pg_dump -Fc` → `@instance/backups/pg/`, 7 daily + 4 weekly), `walter-statedb-backup`
(03:50 UTC), offsite = **restic** `walter-restic-backup` (05:10 UTC, encrypted deduplicated repository on Drive,
snapshots tagged `keep` are never forgotten), monthly restore test `walter-offsite-restore-test.service` (the 3rd)
which runs `walter-restic-restore-test` (restores PG into a disposable database and compares the tables listed in
`@instance/config/backup/backup.toml` `restore_test.compare_tables`). State: `walter-ops backup status`. Restore a
full dump by sections (pre-data, data, post-data), never one `pg_restore -j`: the trigger of the partitioned
`core.events` fires while partitions load.

Regression checks after touching backups, privacy or logs:

```bash
cd /walter/memory && walter-python -m pytest -q tests/
bash scripts/post_repair_smoke_test.sh   # from this skill's folder
```

## Related

- Hermes Desktop private API path, preserved while removing dashboards (Mac localhost9119 → Tailscale8788 → Hermes
  loopback8787; auth env stays 0600 and is never printed): `hermes-desktop-recovery`.
- People / Kardex: `contact-intelligence-systems`; iPhone location: `overland-location-troubleshooting`;
  credentials in logs: `walter-vault-log-masking`.

## References

Still current:
- `references/memory-routing-guardrails.md` — keep `MEMORY.md` from becoming the default dumping ground.
- `references/recall-bench-methodology.md` — measuring retrieval quality (probe panel, judge pitfalls, why absolute
  score thresholds do not work as injection filters).
- `references/agent-memory-graph-patterns.md` — research notes (Graphiti/Zep, Letta, Mem0, Cognee, LightRAG…).
- `references/kardex-psyche-layer.md` — Kardex tables and personality matrices (check against the live schema).
- `references/deep-memory-audit-checklist.md`, `references/vm-audit-cleanup.md` — audit and disk clean-up lists.

Historical (Hindsight era, provenance only): `references/historical-2026-08-architecture.md` (the former body of this
skill), `hindsight-ops.md`, `hindsight-audit.md`, `hindsight-memory-consistency.md`, `hindsight-temporal-graph.md`,
`memory-vector-recall-architecture.md`, `port-service-map.md`, `auto-maintenance.md`, `dedup-and-dreaming-fixes.md`,
`organic-lifecycle.md`, `system-operations.md`, `curator-configuration.md`. The tables, ports and scripts they name no
longer exist. `scripts/post_repair_smoke_test.sh` checks the current stack (read-only).
