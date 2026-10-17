---
name: walter-router-service-boards
description: Use when adding or repairing Walter Router leaderboard collectors, service offer classification, or measured scoring for STT, rerank and embeddings.
---

## Inspect and protect existing state

Work in `/opt/walter-router`. Read `README.md`, `docs/DESIGN.md`, and the relevant migrations before editing. Inspect `git status --short` and `git diff`; preserve existing uncommitted work.

Trace the complete route through `walter_router/collect.py`, `identity.py`, `media.py`, `scoring.py`, `select.py`, `choose.py`, and `alerts.py`. Inspect `models.tasks`, `models.task_benchmarks`, `models.preferences`, and the latest snapshots and offers. Migration `021_service_boards.sql` introduced the service boards; inspect its current state before proposing another migration.

Back up the `models` schema and every file to be changed under `/root/.hermes/backups/<dated-task>/`. Capture the current selections:

```sh
cd /opt/walter-router
for task in stt rerank embeddings; do
    bin/walter-router pick "$task"
done
```

Use `walter_router.db.connect()` with the repository virtualenv for database access. If host `psql` is unavailable, use:

```sh
docker exec -i hindsight-pg psql -U hindsight -d hindsight -P pager=off
```

Never print credentials.

## Collect and classify service measurements

Inspect the registered collectors in `collect.SOURCES`: `aa_stt`, `agentset`, `mteb`, and `openrouter`. Preserve the last good snapshot when a source fails.

Keep source limitations explicit: AA Speech-to-Text measurements collected in this implementation covered English test sets, not French. Agentset supplies quality ELO and latency for rerank and embeddings; MTEB supplies French retrieval measurements. Recheck source coverage before describing current results.

Link benchmark identities to catalog model identities before scoring. Classify offers by service interface: `transcription`, `rerank`, or `embedding`; do not leave them in generic chat/audio categories merely because of catalog placement.

Keep billing dimensions separate. A transcription price per second is not a token price: leave `price_in_1m` unset and normalize the service price explicitly. Preserve source precision: a price of 0.00000333 per second becomes 0.0001998 per minute. Use the canonical unit spelling expected by consumers; this implementation standardized embedding units as `per 1m tokens`.

## Validate parsers and scoring

Use `tests/test_service_boards.py` as the starting point for parser, classification, normalization, and scoring regression coverage. Include realistic Next.js Flight payloads where applicable. Compact JSON fixtures matched the production parser in this session; if whitespace tolerance is required, test and fix the parser explicitly rather than silently assuming it.

Check primary-board eligibility. A model measured only on a secondary board must not qualify for a task that requires primary-board evidence; inspect the task's `requirements.require_primary` setting.

Keep raw measures alongside higher-is-better scoring transforms. Alert text must display measured WER and latency, with their original direction and units. Preserve enough decimal precision to make WER comparisons meaningful.

Run:

```sh
cd /opt/walter-router
venv/bin/python -m pytest -q tests/test_service_boards.py
venv/bin/python -m pytest -q tests
```

## Apply and verify without changing adopted models

After backups and passing tests, apply pending migrations:

```sh
bin/walter-router migrate
```

Collect changed sources and confirm their completion before deriving results. OpenRouter service-page price collection took substantially longer than the other collectors in this session; inspect its exit status and resulting snapshot rather than assuming it completed.

Recompute from stored snapshots without sending notifications:

```sh
bin/walter-router refresh --skip-collect --no-notify
bin/walter-router health
for task in stt rerank embeddings; do
    bin/walter-router dossier "$task"
    bin/walter-router pick "$task"
done
```

Inspect board coverage, candidate eligibility, price units, alert rendering, and pinned selections. A newly measured challenger is a proposal; preserve adopted model and provider preferences until the owner adopts a change. Treat embedding model changes as a separate compatibility decision.

Update `README.md` and append the decision and validation evidence to `/root/.hermes/docs/walter-memory/DECISIONS.md`, backing it up first. Report migration status, test results, collector failures, and whether selections changed.
