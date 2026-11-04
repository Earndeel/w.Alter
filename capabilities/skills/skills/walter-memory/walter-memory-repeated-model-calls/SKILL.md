---
name: walter-memory-repeated-model-calls
description: Use when Walter Memory shows unexpectedly high model usage, rerank bursts, repeated decisions, or unnecessary periodic recomputation.
---

## Attribute calls before changing anything

Load memory context and the relevant memory procedures through the Walter harness. Read `/walter/docs/ARCHITECTURE.md`, `DECISIONS.md` and the Walter Memory section of `RUNBOOK.md` before changing memory behavior. Inspect personal contents through aggregates; never dump messages or credentials.

Use the actual incident date and explicit UTC boundaries. Inspect schemas before assuming column names:

```sh
docker exec -i hindsight-pg psql -U hindsight -d hindsight -c '\d system.model_calls'
docker exec -i hindsight-pg psql -U hindsight -d hindsight -c '\d walter_logs.events'
```

Define a read-only query helper:

```sh
Q() { docker exec -i hindsight-pg psql -U hindsight -d hindsight -c "$1"; }
```

Count by processor, purpose, model, budget and status; include cost and a historical comparison. Example incident query:

```sh
Q "SELECT processor,purpose,model,budget,status,count(*),round(sum(cost_usd),3) usd FROM system.model_calls WHERE at >= '2026-11-03 00:00+00' AND at < '2026-11-04 00:00+00' GROUP BY 1,2,3,4,5 ORDER BY count(*) DESC"
```

Separate bursts from steady traffic. For rerank, group calls separated by more than 60 seconds:

```sh
Q "WITH c AS (SELECT at, CASE WHEN lag(at) OVER (ORDER BY at) IS NULL OR at-lag(at) OVER (ORDER BY at)>interval '60 seconds' THEN 1 ELSE 0 END s FROM system.model_calls WHERE at >= '2026-11-03 00:00+00' AND at < '2026-11-04 00:00+00' AND purpose='rerank'), g AS (SELECT at,sum(s) OVER (ORDER BY at) grp FROM c) SELECT grp,min(at),max(at),count(*) FROM g GROUP BY grp ORDER BY min(at)"
```

Correlate each burst with `walter_logs.events.occurred_at`, session IDs and tool invocations. Inspect event types first rather than assuming a particular tool-event label. Retrieve only the narrowly relevant command through the logs interface. Distinguish benchmark traffic from normal context injection before proposing a fix.

## Trace repeated work to its origin

Inspect callers, scheduled units and processing state. Check whether unchanged inputs are recomputed, whether negative or unsure decisions are persisted, and whether another pass overwrites processing markers.

Known evidence from this incident:

- Two bursts of exactly 82 rerank calls came from two runs of `bench/g1_recall.py`, including a run with `--rerank`; benchmark usage accounted for 164 of 247 calls.
- Whole-window rebuilding repeatedly rewrote unchanged knowledge.
- A flows pass erased the plans marker stored in burst rows.
- Episode attestation repeated questions whose prior verdicts were not retained.

Do not solve these mechanisms solely by lowering frequency or disabling the model.

## Make processing incremental and idempotent

Back up affected files before edits. Use Walter's existing bus and declared module interfaces.

- Emit a knowledge-change event only when semantic content actually changes.
- Recompute only subjects or windows affected by that event.
- Keep queues, cursors and model-decision records in the `processing` schema, separate from knowledge rows.
- Key each decision by its exact effective inputs. Persist refusals, unrelated and unsure outcomes as well as positive decisions. Reuse an outcome while those inputs remain unchanged.
- Keep source polling, deadlines and reconciliation scheduled; drive reactions to changes through the bus.

Verify meaningful behavior: unchanged writes cause no new work, identical questions reuse decisions, changed inputs receive fresh decisions, and processing state survives unrelated knowledge updates.

## Validate production over comparable windows

Record the UTC switch time. Compare equal-duration windows, with the baseline ending before any intervention. Count model calls per processor, decision-cache hits, rewrites, queue backlog and bus progress.

```sh
walter-memory assimilation status
journalctl -u walter-memory-pipeline --since '2026-11-03 20:24:13 UTC' --no-pager -o cat
systemctl start memory-autopilot
```

Check the autopilot score in its latest report. Investigate tracebacks in their full timestamped context: a pool-destructor exception during restart must not be mistaken for a live processing failure. Confirm remaining calls represent new inputs.

Use a systemd unit for delayed measurements; do not leave a terminal background sleep running. Do not claim an hourly improvement from four minutes of observation. Document results in `RUNBOOK.md` and append the dated decision to `DECISIONS.md`; stage only this task's changes in shared working trees.
