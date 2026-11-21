---
name: hindsight-debug-and-repair
category: devops
description: Debug and repair Hindsight memory system for Hermes — diagnosis of common failures (module missing, root PG crash, empty DB) and repair steps.
tags: [hindsight, memory, postgresql, pgvector, debug, hermes]
created: 2026-04-22
---

# Hindsight Debug & Repair

## Always-on rules

- The plugin's valid modes are: `cloud`, `local_embedded`, `local_external`. Always use `"local_external"` with `"api_url"` for external API servers.
- Never put model/provider overrides in `Environment=` lines in the systemd unit. Put ALL config in `EnvironmentFile=` only.
- NEVER `kill -9` the gateway from inside an agent session — it kills the session and forces manual relaunch.
- Use `/metrics` endpoint for internal timings — `trace=true` does NOT expose phase timings.
- **Fix — nuclear option (drop + recreate schema):** **WARNING:** This deletes ALL stored memories. Only do this when changing embedding models.

## Full Stack Audit

See `references/full-stack-audit.md` for the complete step-by-step audit procedure (infrastructure health, data volume, duplicates, systemd timers, crons, script validation, PG/Qdrant drift interpretation).

## References (read with skill_read(name, file_path=...))

- `references/api-schema-and-providers.md` — Read when constructing API requests, querying database tables, or changing component providers.
- `references/architecture-and-setup.md` — Read when inspecting the documented architecture, package versions, deployment configuration, or fresh-install procedure.
- `references/diagnostics-and-tests.md` — Read when running initial diagnostic checks or validating health, integration, recall behavior, and data integrity after repairs.
- `references/failure-diagnosis-and-repair.md` — Read when diagnosing import failures, embedded PostgreSQL crashes, authentication errors, initialization failures, migrations, or provider configuration.
- `references/full-stack-audit.md` — Read for the complete infrastructure, data-volume, duplicate, timer, cron, script-validation, and PG/Qdrant drift audit.
- `references/hindsight-extraction-testing.md` — Read when testing Hindsight memory extraction.
- `references/pitfalls.md` — Read before applying repairs to check documented configuration traps, restart hazards, API quirks, and operational caveats.
- `references/search-and-performance.md` — Read when measuring latency, inspecting Prometheus metrics, or investigating Qdrant, hybrid search, and reranker performance.
