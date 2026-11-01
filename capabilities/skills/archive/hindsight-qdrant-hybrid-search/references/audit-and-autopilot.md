## Full Memory Stack Audit Runbook

Use this when asked for a complete memory-system checkup, not just a single endpoint fix. Audit the whole chain: config, systemd/Docker services, endpoints, PG/Qdrant integrity, read/write/retain/recall paths, benchmarks, logs/timers, cleanup, and final risk report.

### Audit order

1. Load `hindsight-debug-and-repair`, `hindsight-qdrant-hybrid-search`, and `hermes-agent` when Hermes/Hindsight configuration is involved.
2. Redact secrets before displaying config/env/logs. Never print API keys, tokens, full connection strings, or auth headers.
3. Check services and ports:
   - `systemctl status hindsight-api hybrid-search write-worker dream-cycle.timer`
   - `docker ps` for `qdrant` and `hindsight-pg`
   - health endpoints: `:8888/health`, `:8889/health`, `:8890/health`, Qdrant `:6333`
4. Inspect PG via schema introspection first. Do not assume columns like `source` exist. Confirm counts, embedding nulls/dimensions, extensions, duplicate groups, recent rows, async operation status, and orphan references in `unit_entities`/`memory_links`.
5. Inspect Qdrant collections (`memories`, `entities`), point counts, vector size/distance, and payload source distribution. Compare PG vs Qdrant cardinality, but report whether the difference is expected active-index behavior or a reconciliation risk.
6. Test runtime paths with process-level timeouts:
   - Use `curl --max-time` for retain/recall/write-worker tests. Python client timeouts can still hang during external LLM/provider calls.
   - Recall: `POST /v1/default/banks/walter/memories/recall` and `POST http://127.0.0.1:8889/recall`.
   - Retain: `POST /v1/default/banks/walter/memories` with `{"items":[...]}`.
   - Write worker: `POST http://127.0.0.1:8890/process` with durable, realistic facts. Prompts explicitly marked `test`, `temporary`, or `audit` may correctly return `facts=0` due to the extractor prompt.
7. Run official validation:
   - `python3 /root/.hermes/scripts/test_hindsight.py --verbose`
   - `python3 /root/.hermes/scripts/bench_hindsight.py`
8. Cleanup any audit artifacts explicitly created during the audit. Do not trust test scripts to fully clean themselves: after `test_hindsight.py` / `bench_hindsight.py`, explicitly check PG for markers like `TEST_SUITE:`, `BENCHMARK`, `MEMCHECK`, and `AUDIT_MEMORY_CHECK`. For PG, delete related rows from `memory_links` (`from_unit_id`/`to_unit_id`) and `unit_entities` (`unit_id`) before deleting `memory_units`. For Qdrant, scroll small collections and delete exact marker payload matches by point ID; snapshot/count before and after.
9. Scan maintenance/logs:
   - `journalctl -u hindsight-api -u hybrid-search -u write-worker --since '24 hours ago' -p warning..alert`
   - `docker logs --since 24h qdrant` and `docker logs --since 24h hindsight-pg`
   - `systemctl list-timers --all | grep -Ei 'hindsight|memory|dream|hermes'`
   - cron files only if relevant; this setup mainly uses `dream-cycle.timer`.
10. Final report should be concrete: OK/attention/critical by component, measured latencies, data integrity status, cleanup performed, risks, and prioritized actions.

### Audit findings to specifically check for

- PostgreSQL log spam from missing maintenance functions, e.g. repeated `SELECT * FROM schemas_with_pending_work()` every ~0.5s. If present, identify the caller before patching. Safe repair pattern: add an idempotent SQL helper function (`schemas_with_pending_work() RETURNS SETOF text`) and also patch the Python poller with a fallback/cache so the worker does not re-enter an error loop if the DB helper disappears.
- For PostgreSQL commands, prefer SQL via stdin with `docker exec -i hindsight-pg psql -U hindsight -d hindsight -t -A -F '|' -P pager=off`; inline escaped newlines can produce confusing `invalid command \nSELECT` errors.
- Inspect table schemas before cleanup. In this deployment `memory_links` uses `from_unit_id` and `to_unit_id`, not `source_unit_id`; deleting artifacts with the wrong column only creates noisy PG errors.
- Qdrant telemetry errors to `https://telemetry.qdrant.io/` are usually non-blocking noise. Disable telemetry or ignore if all local endpoints are healthy.
- `write-worker` may log `extracted_facts len=1` but `Normalized 0 facts` when Qwen returns an alternate schema like `type + subject + context + attribute + value + confidence`. Patch `normalize_facts()` to synthesize a `fact` string from those fields instead of dropping it silently.
- When testing the write worker, avoid content words like `test`, `temporary`, or `audit` if the goal is to verify durable extraction; the extraction prompt may correctly filter them as non-durable and return zero facts.
- For HTTP checks that may touch external LLM providers, use `curl --max-time`; Python `urllib`/client tests can hang until the outer harness timeout.
- If a Docker json log grew due to a loop, rotate/copytruncate it or configure Docker `json-file` rotation (`max-size`, `max-file`) before relying on `docker logs`; direct tail of the log file can be safer than scanning a huge log.
- Duplicate counts are not automatically delete-worthy. Report exact and near duplicates, but prefer dream-cycle/consolidation merge/invalidation over destructive manual deletes.
- PG/Qdrant count mismatches require interpretation. Qdrant may be the active fast index while PG stores broader history. Check `pg_unique_texts_absent_from_qdrant` in the reconcile dry-run to quantify drift. If Qdrant is intended to mirror PG, run reconciliation/migration. The dual-path recall architecture means PG-only entries ARE searchable (via port 8888) but lack proper vector scoring (scores=0.000).

## Memory Autopilot Supervisor (non-destructive)

Use this when Lucas wants the memory system to maintain itself invisibly without mutating memory data. It complements, but does not replace, the nocturnal dream cycle.

Installed pattern:
- Main script: `/root/.hermes/scripts/memory_autopilot.py`
- Policy helper: `/root/.hermes/scripts/memory_policy.py`
- Safe cleanup: `/root/.hermes/scripts/memory_safe_cleanup.py`
- Guarded exact PG dedup: `/root/.hermes/scripts/hindsight_pg_exact_dedup.py`
- Service: `memory-autopilot.service` with `--autofix safe`
- Timer: `memory-autopilot.timer`
- Guarded service/timer: `memory-guarded-maintenance.service` / `.timer`
- Reports: `/root/.hermes/logs/memory-autopilot/latest.json`, `alert-latest.json`, `status.log`, `service.log`, `safe-cleanup-latest.json`, `pg-exact-dedup-latest.json`
- Schedule: safe autopilot runs nightly around 06:10 UTC (`RandomizedDelaySec=300`) as a post-flight check after dream-cycle and guarded maintenance; guarded exact dedup runs daily around 05:37 UTC after dream-cycle.

What it does:
1. Detects if `dream-cycle.service` is active and defers to avoid competing with consolidation.
2. Runs stack checker and small `/recall` quality probes.
3. Tracks PG/Qdrant counts, embedding-null count, duplicate pressure, pending async ops, and PG↔Qdrant drift.
4. Runs `/root/.hermes/scripts/hindsight_reconcile_dryrun.py` periodically (default every 12h) and stores only a compact summary in the main report.
5. In `--autofix safe`, automatically cleans generated test artifacts, deletes Qdrant `invalidated=true` points, restarts dead core memory services, and rotates large Docker logs.
6. In guarded maintenance, deduplicates exact normalized PG `memory_units` with snapshot + bounded apply: repoints `unit_entities` and `memory_links`, avoids self-links/duplicate links, then deletes only verified duplicate rows.
7. Treats PG/Qdrant count drift as expected when Qdrant is healthy under the active-index policy: PG is broad history/audit; Qdrant is the active/canonical fast recall set.

Validation commands:
```bash
/root/.hermes/hermes-agent/venv/bin/python3 -m py_compile /root/.hermes/scripts/memory_autopilot.py
/root/.hermes/hermes-agent/venv/bin/python3 /root/.hermes/scripts/memory_autopilot.py --mode quick --output /root/.hermes/logs/memory-autopilot/latest.json
systemd-analyze verify /etc/systemd/system/memory-autopilot.service /etc/systemd/system/memory-autopilot.timer
systemctl start memory-autopilot.service
systemctl show memory-autopilot.service --property=Result,ExecMainStatus,ActiveState,SubState --no-pager
systemctl list-timers --all --no-pager | grep -Ei 'memory-autopilot|dream-cycle|hindsight-stack-check|hermes-docker-log-rotate'
```

Pitfalls:
- Default mode is observe-only, but production uses `--autofix safe`; safe fixes must remain limited to unambiguous hygiene (test markers, invalidated Qdrant points, dead service restart, log rotation).
- Guarded dedup must snapshot before apply and stay bounded (`--limit-groups`, `--max-delete`). Never do semantic PG dedup or mass backfill in the hourly timer.
- Do not read or print env files/drop-ins containing credentials. Reports must redact secret-like strings and should store counts/snippets only. Redact generated dedup reports too, because exact duplicates can include credential memories.
- Do not overlap with `dream-cycle.service`; defer if it is active.
- Treat PG/Qdrant drift as expected while Qdrant recall probes pass and Qdrant is the active fast index. Backfill only classified recent/high-value facts, never the whole PG history blindly.
