---
name: hermes-memory-ops
category: devops
description: Use when diagnosing or maintaining Walter Memory, PostgreSQL/pgvector, raw agent logs, backups, synthesis privacy or memory supervision.
tags: [memory, hindsight, qdrant, postgresql, cron, maintenance, watchdog]
created: 2026-06-07
---

# Hermes Memory Operations

## Current operating procedure — verified 2026-10-17

This section supersedes the historical August architecture and commands below. Qdrant, hybrid-search,
write-worker/write-bridge, pg-qdrant-sync, dream-cycle and Jarvis are retired since 2026-10-01.
Do not restart them or install Qdrant clients to satisfy an old smoke test.

1. Read /root/.hermes/docs/walter-memory/{ARCHITECTURE,DECISIONS,RUNBOOK}.md.
   Durable truth is core.events + core.objects in hindsight-pg (127.0.0.1:5433).
   Hindsight is replaceable cognition; Kardex is the social schema; vectors use PostgreSQL/pgvector.
   Use Walter Memory lib/gateway for writes. Never patch the upstream Hermes checkout.
2. Run /usr/local/bin/walter-memory health, systemctl status walter-logs-watch and
   systemctl status walter-memory-gateway. Use PG via docker exec without printing secrets.
   For Hermes gateway use systemctl --user, not the system service.
3. Raw journal = walter_logs, across all runtimes including Hermes state.db/profiles and Codex.
   core.events describes Monsieur's life. Do not mistake raw Vault exports for walter_logs backup.
   PG dumps include both. Use the walter-logs-ingestion skill for coverage/checkpoint diagnosis.
4. Maintenance: /opt/walter-memory/venv/bin/python -m walter_memory.hygiene --kind ephemeral --limit 200
   is DRY-RUN by default; --apply snapshots prior tags, audits and adds quarantine:noise in Hindsight PG.
   Never delete canonical/raw logs to clean recall noise. ephemeral-sweeper.service is versioned under
   /opt/walter-memory/systemd; compatibility scripts are links to /opt/walter-memory/ops.
5. After a memory repair run systemctl start memory-autopilot and inspect
   /root/.hermes/logs/memory-autopilot/latest.json. Autopilot now incorporates walter-memory health
   and cleanup failures; warning score90 was real on Oct17 (Beeper failed media, low provider balance).
   Do not reinterpret a score alone as full business health.
6. L3 synthesis must exclude local_only before the call, carry the strictest included source class
   through walter_memory.llm and its derived item/search chunk, and omit private titles.
   privacy.tighten_derived_sources defaults dry-run; apply only after metadata backup, tightening
   derived/chunk classes and quarantining any previously published Hindsight projection.
7. Backups: walter-pg-backup + walter-statedb-backup + walter-offsite-backup; monthly
   walter-offsite-restore-test downloads/decrypts and restores PG into a disposable database,
   checks main SQLite, module manifest and Bitwarden item count.
   backup_bundle discovers all /opt/walter-* and integration configs, snapshots profile DBs,
   inventories Python packages and verifies SHA-256, links, modes and mandatory entrypoints.
   Venvs and rebuildable model weights are excluded. Raw Vault bytes already reside on Drive.
   A verified bundle is not yet proof of a complete installation on a clean VM.
8. Preserve Desktop's private API while removing dashboards: Mac localhost9119 -> Tailscale8788 ->
   Hermes loopback8787. See hermes-desktop-recovery. Auth env must stay0600 and never be printed.

Regression checks for this repair:
cd /opt/walter-memory &&
venv/bin/python -m pytest -q tests/test_backup_bundle.py tests/test_extract_privacy.py tests/test_hygiene.py tests/test_logs.py
18 tests passed on 2026-10-17. Restore test succeeded that day: PG, main state.db, 12 modules,
9 profile SQLite snapshots and 9 Python environment inventories.

## Historical material below — August architecture, not an execution plan

Keep the following incident descriptions and references for provenance. Any Qdrant, legacy port,
provider/model, cron or deletion command below must be checked against the current runbook first.


## When to Use

- Diagnosing why memory isn't growing (no new rows in `memory_units`)
- Cron jobs failing with provider/credit errors
- PG↔Qdrant drift or sync issues
- VM disk audit and cleanup
- Memory stack health verification
- Understanding the current memory architecture

## Current Architecture (updated 2026-08-21)

```
Layer 0: MEMORY.md (cap 2200) + USER.md (cap 1375) — injected every turn
Layer 1: Hindsight Recall via Hybrid Search (:8889) — Qdrant + ZeRank-2 reranker
Layer 2: PostgreSQL (hindsight-pg container) — source of truth
Layer 3: Write Path — Hindsight API (:8888) + Write Worker (:8890)
Layer 4: Maintenance crons — on Kie/gemini-3.5-flash (NOT OpenRouter)
Layer 5: Sessions DB (state.db, SQLite FTS5)
Kardex: Social memory (schema kardex in hindsight-pg, 41 tables)
```

**⚠️ Schema change (verified 2026-08-21):** facts live in `memory_units`
(~30k rows, columns: text, embedding, fact_type, tags, proof_count…), NOT
`memory_facts` (frozen since 2026-07-04, kept only for `qdrant_sync_status`
legacy reads). The API recall route is
`POST /v1/default/banks/{bank}/memories/recall` (NOT `/recall`, which 404s).
Write contract: `{"items":[{"content": "..."}]}` (not `text`).
`qdrant-client` must be pinned to the Qdrant server version (1.17.1) or the
client warns on every start.

**✅ Fixed (2026-08-21):** `units_qdrant_sync.py` (jarvis) now indexes
`memory_units` → Qdrant `memories` using PG-stored embeddings (no API cost),
state in `public.units_sync_state`, wired into the 5-min `pg-qdrant-sync.timer`
via systemd override. Qdrant is now a 1:1 projection of PG (29 952 points).
Legacy duplicates (7 359) and orphans (298) were purged. Ephemeral "run log"
facts are swept daily at 04:50 by `ephemeral-sweeper.timer`
(`purge_ephemeral_facts.py`, archive at `~/.hermes/membench/purge_archive.json`).
The Telegram watchdog cron (fa8c6bdcc442) is REACTIVATED (*/5min, was silently
paused 2026-08-10→21 which let the Aug 19 venv incident run 2 days unnoticed).
Recall bench: `~/.hermes/scripts/recall_bench.py` (14 probes, 5 categories,
results in `~/.hermes/membench/`).

Services: hindsight-api, hybrid-search, write-worker (all systemd)
Docker: qdrant (6333), hindsight-pg (5432 internal), flaresolverr, webtop

## Critical Pitfall: Cron Provider Resolution

Jobs with `model=null` / `provider=null` inherit from config.yaml, which resolves
through `fallback_providers`. If fallback points to OpenRouter with no credits,
ALL cron jobs fail silently — even if the main provider (kie/aiprimetech) works fine.

**Detection:** `hermes cron list` shows `error: 402` on multiple jobs.

**Fix:** Set explicit model/provider on each cron job:
```
cronjob action=update job_id=<id> model={"model": "gemini-3.5-flash", "provider": "kie"}
```

**Prevention:** Never create LLM-driven cron jobs without explicit model. Use `no_agent=true`
with scripts for jobs that don't need reasoning (health checks, syncs, data collection).

## Health Check Stack

### Quick verification (run manually)
```bash
curl -s http://127.0.0.1:8888/health   # Hindsight API
curl -s http://127.0.0.1:8889/health   # Hybrid Search (shows memories_count)
curl -s http://127.0.0.1:8890/health   # Write Worker
curl -s http://127.0.0.1:6333/collections  # Qdrant
docker exec hindsight-pg psql -U hindsight -d hindsight -c "SELECT COUNT(*) FROM memory_units WHERE created_at > NOW() - INTERVAL '7 days';"
```
Full post-repair battery: `bash /root/.hermes/skills/devops/hermes-memory-ops/scripts/post_repair_smoke_test.sh [--write-test]`
— checks the 4 health endpoints, Qdrant point count, PG write-path activity,
and optionally the write→recall round-trip using the real API contracts
(`--write-test` inserts one test fact; default is read-only).

### Automated watchdog
- Script: `~/.hermes/scripts/memory_health_check.sh`
- Cron: job fa8c6bdcc442, every 30min, no_agent, Telegram delivery
- Pattern: silent when healthy, alerts on failure, auto-restarts services

### PG↔Qdrant sync verification
```bash
cd /root/.hermes/services/jarvis && python3 pg_qdrant_sync_worker.py --health
# Shows: coverage_pct, pending_outbox, sync_errors
```

## Write Path Flow

1. `hindsight_retain` tool or `POST /v1/default/banks/walter/memories` → creates document in PG
2. Hindsight API worker (polls every 30s) → processes async_operation
3. Extraction via Gemini Flash Lite (free) → creates `memory_units`
4. Embedding via Gemini Embed 2 → upserts to Qdrant `memories` collection
5. Consolidation (periodic) → dedup, merge, entity graph enrichment

**Key insight:** Retain is document-first. Short content may not produce facts.
The extractor needs substantive text to generate structured facts.

## VM Disk Cleanup (safe targets)

| Path | Typical size | Action |
|---|---|---|
| `~/.hermes/heapdumps/` | 5+ GB | Delete all (April dumps, never needed) |
| `~/.hermes/logs/memory-autopilot/` | 1+ GB | `find ... -mtime +7 -delete` |
| `~/.hermes/logs/hindsight-api.log` | 100+ MB | Truncate (WORKER_STATS noise) |
| `~/.cache/uv` | 10+ GB | `uv cache clean` (reconstructs on demand) |
| Docker dangling images | 5-10 GB | `docker image prune -a -f` (after checking) |
| `~/.hermes/state-snapshots/` | ~1 GB | Delete once update validated |
| `*.bak*`, `*.corrupted-*`, `auth.json.tmp.*` | misc | Safe to remove |

**Never touch:** hermes-agent/venv (6 GB, needed), state.db (sessions), .cache/huggingface (models)

## Qdrant Collections

- `memories` — active, HNSW indexed, 768d Gemini Embed 2. The only read-path collection.
- `entities` — exists but NOT queried by any service. Graph lookup uses PG directly.
- `memories_local` — deleted 2026-06-07 as dead, but found RESURRECTED on 2026-08-21 (8,217 points, writer unknown). On no read path; identify the writer before deleting again

## Cron Jobs Reference

| Job | Type | Provider | Schedule | Delivery |
|---|---|---|---|---|
| Memory Health Check | no_agent script | N/A | */5 * * * * | telegram — REACTIVATED 2026-08-21 (was silently paused 2026-08-10→21, which let the Aug 19 venv incident run 2 days unnoticed). Script v2 checks 8888/8889/8890/8891/8896, Qdrant, PG, systemd services, and PG↔Qdrant drift via `units_sync_state` (not legacy memory_facts). Never leave this paused. |
| Memory Dreaming | LLM | kie/gemini-3.5-flash | 0 4 * * * | local |
| Memory External Connectors | LLM | kie/gemini-3.5-flash | 0 5 * * * | local |
| location-insights | LLM | kie/gemini-3.5-flash | 0 */6 * * * | local |
| AI Free Offers Watchdog | LLM | kie/gemini-3.5-flash | 0 0 * * * | telegram |
| AI Offers Collector | no_agent script | N/A | 45 23 * * * | local |
| Skill Intelligence Loop | LLM | kie/gemini-3.5-flash | 0 3 * * * | local |

## MEMORY.md / USER.md Routing Guardrails

### Problem
Hermes agents tend to use the `memory` tool as the easiest persistent sink, which makes `MEMORY.md` absorb procedures, task history, infra notes, URLs, ports, and other material that should live elsewhere. Because `MEMORY.md` and `USER.md` are injected into future turns, this creates recurring prompt bloat and stale self-instructions.

A subtle failure mode: hardening only `target='memory'` is insufficient. The `memory` tool maps `target='user'` to `USER.md`, so an agent can still persist workflow/style corrections automatically through the user-profile path even when `MEMORY.md` is guarded.

### Corrective pattern
- Treat `MEMORY.md` as a near-empty critical-facts buffer only.
- Route stable user preferences to `USER.md`; identity/opmode rules to `SOUL.md`; historical lessons to Hindsight or `EVOLUTION.md`; procedures/architecture to skills; credentials to vault.
- Put enforcement at the tool boundary, not just in prompt prose: reject `target='memory'` writes that look like procedures, infra, secrets, session history, URLs/ports/commands, or long narratives.
- When investigating unwanted persistence, check `memory.write_approval` in `config.yaml`; if false, writes to both `MEMORY.md` and `USER.md` commit directly. Set it true to stage writes for `/memory pending` review.
- Tighten the `memory` tool schema so the model sees the routing hierarchy before it calls the tool.
- Verify with a temp Hermes home: infra/procedure memory writes fail, while `target='user'` preference writes pass or stage depending on `memory.write_approval`.

See `references/memory-routing-guardrails.md` for the compact implementation pattern and verification recipe.

## Memory Duplication in Hindsight

### Problem
Hindsight's extraction + retention pipeline can produce near-duplicate facts when the same information gets retained across multiple sessions with minor phrasing variations. Since the Hindsight block is injected into the system prompt on every LLM call, duplicates compound into permanent payload bloat.

### Real example (June 2026)
| Fact | Occurrences | Language mixing |
|---|---|---|
| "MiMo cache hit = $0.0036/M, 99% cheaper" | 5× | FR variants |
| "cache_control headers → Xiaomi parsing errors" | 2× | EN/FR |
| "API Xiaomi directe $0.18 blended (7:2:1)" | 2× | FR variants |
| "UltraSpeed registration 9-23 June 2026" | 2× | FR variants |

**Waste:** ~500 tokens per LLM call, every call.

### Root causes
1. **Language mixing** — Same fact retained in both FR and EN across sessions
2. **Granularity stacking** — "X costs Y" AND "X costs Y, which is Z% cheaper"
3. **Session re-discovery** — Agent doesn't recall the fact is already stored, retains again
4. **hindsight_recall rate limits** — 429 on Vertex embeddings prevents pre-write dedup check

### Detection triggers
- Memory block > 1,500 tokens or 15+ entries → scan for semantic duplicates
- Same dollar amount or percentage appearing 3+ times
- Same claim in two languages

### Mitigation
- Retain facts in ONE language (match user's primary)
- Check the injected memory block visually before re-retaining
- No Hindsight delete/dedup API exists — this is structural until upstream adds it
- **ROI context:** Duplication costs ~500 tok/call. Conversation history costs ~50K+/session. Prioritize accordingly.

## 2026-08-19 venv incident (resolved 2026-08-21)

`qdrant_client` (and `sentence_transformers`) vanished from
`/root/.hermes/hermes-agent/venv` on 2026-08-19 ~15:36 UTC — likely a venv
rebuild that dropped non-core deps. 4 services crash-looped for 2 days
(hybrid-search: 161k restarts) with NO alert: the Telegram watchdog cron
(fa8c6bdcc442) was paused since 2026-08-10. Fix:
`venv/bin/pip install 'qdrant-client==1.17.1' sentence-transformers`, restart
services, `systemctl reset-failed`. **Lesson:** never let the watchdog stay
paused; a green main chat does not mean a green stack (8888 has its own deps).

## Failed Consolidations Recovery (transient network errors)

**Symptom:** `GET :8888/v1/default/banks/walter/operations?status=failed` shows failed `consolidation` ops with `ConnectTimeout` / `Temporary failure in name resolution` / `Server disconnected without sending a response` (transient DNS or embeddings-API blips).
**Fix (one call, no restart, no config change):**
```bash
curl -s -X POST http://127.0.0.1:8888/v1/default/banks/walter/consolidation/recover \
  -H 'Content-Type: application/json' -d '{}'
# Returns {"retried_count": N} — then verify all recent ops are "completed":
curl -s "http://127.0.0.1:8888/v1/default/banks/walter/operations?limit=10"
```
Confirmed 2026-07-04: 14 failed consolidations → recover retried 18 ops → all completed. Transient failures need the recover endpoint, not config changes or restarts.

## Memory Injection & Prompt-Cache Safety (audit finding, 2026-07-04)

Hindsight prefetch is injected EPHEMERALLY into the current turn's USER message at API-call time (`agent/conversation_loop.py` ~line 791: `build_memory_context_block` appended to a copy of the user msg; original never mutated, nothing persisted to session). It is NOT in the system prompt. Consequence: memory injection does NOT invalidate Anthropic prompt caching — the system prompt stays byte-stable and cached at 0.1x price. Do not "optimize" by moving injection or shrinking recall budget for cache reasons; the design is already cache-optimal. With recall_budget=low (recall_max_tokens 600 since 2026-08-21, was 1200) + flash-lite extraction, Hindsight is <1-2% of total LLM spend — not a cost lever. The real cost lever is orchestrator/executor delegation discipline (see walter-operating-mode rule 9).

## Pitfalls

1. `hindsight-api.log` fills fast with WORKER_STATS every 30s — truncate periodically
2. PG `qdrant_sync_status` ('synced'/'deleted'/'pending') exists on legacy `memory_facts` ONLY — table frozen since 2026-07-04; `memory_units` has no such column ('deleted' meant superseded, not lost)
3. Sync worker eligibility: only active+canonical+non-critical privacy facts are synced
4. Write worker (8890) is PASSIVE — Hindsight API (8888) is the active poller
5. `memories_local` should not be recreated — it was a dead-end experiment
6. LanceDB (`~/.hermes/lancedb-gemini/`) fully superseded by Qdrant — deleted 2026-06-07
7. `walter-brain` system obsolete — all functionality covered by Hindsight + Kardex
8. TUI processes can accumulate as phantoms (1-2 days old) consuming ~300MB each — ask user before killing
9. Neo4j installed but inactive — 624 MB, consider removal if unused
10. Security scanner blocks patches on `hindsight-debug-and-repair` skill (45 findings) — use this skill for new operational learnings instead
11. Hindsight accumulates near-duplicate facts over time (same claim, different phrasing). Example: "cache hit = $0.0036/M" appeared 5× in the injected memory block. ~500 tokens wasted per call. No dedup API exists — periodic manual audit is the only mitigation. See §Memory Duplication below.
12. Ephemeral "run log" facts (proc_ ids, "N/N tests", exit codes, durations) pollute recall for ANY tech query and chase out durable preferences. Swept daily 04:50 by `ephemeral-sweeper.timer` (`purge_ephemeral_facts.py`, reversible archive in `~/.hermes/membench/purge_archive.json`). If relevance degrades again, check for a new ephemeral pattern BEFORE blaming the retriever.
13. When probing the API by hand, use the REAL contracts: recall = `POST /v1/default/banks/{bank}/memories/recall` with `{"query": ...}`; write = `{"items":[{"content": ...}]}`. A bare `/recall` returns 404 that naive parsers swallow as "0 results" — always print HTTP status in test scripts.
14. systemd drop-in overrides: `mkdir -p /etc/systemd/system/<svc>.service.d/` BEFORE writing override.conf, then `daemon-reload`. Writing the conf first fails silently-ish and the old ExecStart keeps running.

---

## Hindsight and Vector Recall Branches

This umbrella absorbs the Hindsight/memory micro-skills that were really operational branches of the same memory stack:

- `hindsight-audit` — inventory, drift detection, scaling thresholds, and API field quirks for Hindsight PG/Qdrant audits.
- `hindsight-memory-consistency` — PG↔Qdrant repair, especially distinguishing raw `memory_units` history from active canonical facts.
- `hindsight-temporal-graph` — PG-first temporal graph/provenance sidecar planning and troubleshooting.
- `memory-vector-recall-architecture` — dual vector recall with quality embeddings plus low-latency local voice embeddings.

Use the class-level workflow here first: identify the layer (MEMORY.md/USER.md, Hindsight API, PG, Qdrant, hybrid search, write worker, cron), prove health at that layer, then consult the corresponding reference for session-specific details.

## Support Directory Map

For advanced, session-specific details and operational maintenance procedures, consult the following support files:

- `references/curator-configuration.md`: Curator model selection, config paths, dry-run workflow, and consolidation pass details.

- `references/hindsight-ops.md`: Full troubleshooting guide for Hindsight memory system, embedding APIs, and service restarts.
- `references/auto-maintenance.md`: Autonomous cron-driven scripts for memory deduplication, dreaming, and DB integrity.
- `references/organic-lifecycle.md`: Guidance on how facts decay, consolidate, and rise in importance dynamically.
- `references/system-operations.md`: Deep database structures, VM audits, schema tables, and cleanup targets.
- `references/dedup-and-dreaming-fixes.md`: Specific troubleshooting protocols for dreaming pipeline and deduplication.
- `references/vm-audit-cleanup.md`: Clean-up lists and commands for space reclamation.
- `references/kardex-psyche-layer.md`: Deep specification of Kardex schema tables and personality matrices.
- `references/memory-routing-guardrails.md`: Compact policy and implementation pattern for preventing `MEMORY.md` from becoming the default persistent dumping ground.
- `references/agent-memory-graph-patterns.md`: Research-backed patterns from Graphiti/Zep, Letta, LangMem, Mem0, Cognee, LightRAG/GraphRAG, and Apache AGE for improving W.Alter's memory architecture without defaulting to a platform migration.
- `references/port-service-map.md`: Complete port-to-service mapping for the W.Alter memory stack. Every port, bind address, service name, and health endpoint. Load this before any diagnostic session to orient yourself.
- `references/recall-bench-methodology.md`: How to measure retrieval quality objectively — 14-probe panel design (`~/.hermes/scripts/recall_bench.py`, results in `~/.hermes/membench/`), judge pitfalls (keyword judges produce false negatives; always eyeball top-3), and measured findings: score bands are flat (~0.67–0.82) so ABSOLUTE score thresholds are NOT viable injection filters; the engine fills its quota unconditionally (no abstention mechanism); corpus hygiene dominates ranking quality — purge ephemeral facts before touching the retriever.

## Read-Only Memory Stack Audit

When asked to audit the memory stack without making changes, run these checks in parallel batches, then produce a structured report.

### Audit Checklist

**Discovery batch** (run in parallel):
- All memory-related systemd services: `systemctl list-units --type=service --all --no-legend 'hindsight*' 'hybrid*' 'write-worker*' 'dream-cycle*' 'memory-*' 'jarvis-*' 'pg-qdrant*' 'walter*' 'user-profile*'`
- Docker containers: `docker ps -a`
- Listening ports: `ss -tlnp | grep -E '888[0-9]|889[0-9]|6333|5432'`
- Systemd timers: `systemctl list-timers --all --no-legend | grep -iE 'hindsight|memory|dream|jarvis|walter|pg-qdrant'`

**Health & failures batch** (run in parallel):
- Health endpoints on 8888, 8889, 8890, 8891, 8896
- Qdrant collections: `/collections` then per-collection details
- Failed service journalctl: dream-cycle, user-profile-compiler
- User-profile compiler logs: `/root/.hermes/logs/user-profile-compiler/service.log`

**Metrics batch** (run in parallel):
- PG: DB size, table sizes + row counts + dead tuples, WAL position, connection count, vacuum stats
- Qdrant: per-collection point count, indexed vectors, dimension, status
- Non-secret config: `/root/.hermes/hindsight/config.json`
- System: `df -h /`, `free -h`, `uptime`, `docker stats --no-stream`
- Service memory from systemd: `Memory` and `CPU` lines

**Deep diagnostics batch:**
- Container memory limits: `docker inspect --format '{{.HostConfig.Memory}}' hindsight-pg qdrant`
- Qdrant storage: `docker exec qdrant du -sh /qdrant/storage/collections/*`
- PG replication slots: `SELECT * FROM pg_replication_slots;`

### Audit Report Structure

Produce a report with these 9 sections, in French when the user requested French:
1. **Services actifs/sains** — table: service name, port, bind, memory, CPU, PID
2. **Services en échec** — error, root cause, impact
3. **Conteneurs Docker** — status, uptime, mem usage vs limits
4. **Health endpoints** — response codes and key fields
5. **Bases de données** — PG sizes/rows/dead tuples; Qdrant collections/points/indexed
6. **Timers** — frequency, last run, success/failure
7. **Ressources système** — disk, RAM, load
8. **Anomalies** — ranked Critique/Moyenne/Faible, each with impact and fix
9. **Points positifs** — what's working well

## Common Pitfalls

### psycopg2 absent du venv hermes-agent
**Symptômes :** `dream-cycle` et `user-profile-compiler` échouent à chaque tick du timer avec `ModuleNotFoundError: No module named 'psycopg2'`. Les logs de user-profile-compiler sont dans `/root/.hermes/logs/user-profile-compiler/service.log`.
**Correction :** `pip install psycopg2-binary` dans `/root/.hermes/hermes-agent/venv`.
**Impact :** pas de consolidation nocturne des mémoires, pas de mise à jour du profil utilisateur.

### hindsight-pg saturation mémoire
**Symptôme :** `docker stats` montre >85% de la limite mémoire (1 GiB par défaut). OOM imminent.
**Correction :** `docker update --memory 2g hindsight-pg` ou modification du compose file.

### WAL PostgreSQL anormalement élevé
**Symptôme :** `pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0')` > 10 GB.
**Causes :** checkpointing insuffisant, replication slot orphelin, `wal_keep_size` trop grand.
**Correction :** `CHECKPOINT;` manuel puis ajustement de `wal_keep_size`.

### Entités Qdrant non indexées
**Symptôme :** collection `entities` a des points mais `indexed_vectors_count: 0`.
**Cause :** seuil d'indexation par défaut = 10 000 points. En dessous, c'est de la force brute.
**Impact :** négligeable avec <1000 points.
