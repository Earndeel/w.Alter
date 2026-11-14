---
name: walter-memory-triage-filtering
description: Use when Walter Memory triage spends model calls on irrelevant incoming messages or needs deterministic filters before model invocation.
---

## Diagnose the actual caller

Resolve the module with `walter path memory`. Inspect `walter_memory/triage.py`, `config/triage_rules.json`, and the triage invocation in `walter_memory/assimilation.py` and `walter_memory/pipeline.py`. Attribute calls by processor and purpose, not just model name: the router can change models.

Use `walter-python` and `walter_memory.db.connection` for database queries. Inspect aggregates without dumping message bodies or participant identities:

```sql
SELECT processor, purpose, model, count(*) AS calls,
       round(sum(cost_usd), 4) AS cost
FROM system.model_calls
WHERE at > now() - interval '24 hours'
GROUP BY 1, 2, 3 ORDER BY calls DESC;

SELECT payload->'context'->>'network' AS network,
       payload->'context'->>'thread_kind' AS kind,
       model_action, action, count(*) AS decisions,
       count(*) FILTER (WHERE model IS NOT NULL) AS model_decisions
FROM triage.decisions
WHERE occurred_at > now() - interval '7 days'
GROUP BY 1, 2, 3, 4 ORDER BY decisions DESC;
```

Inspect context fields `monsieur_messages_30d` and `monsieur_mentioned` to distinguish inactive groups from conversations involving Monsieur. Check whether existing deterministic ignores happen only after the model call: that changes the outcome without saving inference.

## Settle eligible decisions before inference

Back up the source and configuration under the instance's `backups/changes/` before editing; inspect git status to preserve unrelated work.

The session introduced `_without_model(r, ev, ctx)`, called in `run()` immediately after `_thread_context(...)`, before the model invocation. Inspect the current implementation before extending it.

Monsieur's configured policy is `silent_group_networks: ["line"]`: ignore a Line group without calling the model only when Monsieur has sent no messages there in 30 days and is not mentioned. Keep this network list configurable. Preserve the existing priority of muted threads and VIP exceptions; do not broaden the rule to direct messages or other networks implicitly.

Record deterministic decisions through the normal decision persistence path, including context and an explanatory rule, without claiming a model produced them. Preserve downstream action guards and shadow behavior. Do not delete source events or reset historical decisions to demonstrate the filter.

## Validate behavior and reload the caller

Use `tests/test_triage_rules.py` for focused cases: eligible inactive Line group, recent participation, mention, direct message, another network, muted thread, and VIP exceptions. Assert that eligible decisions bypass the model and that exceptions still reach the appropriate existing path. Replay historical contexts without invoking the model or mutating historical records to estimate coverage.

Find the process that actually imports triage before restarting:

```bash
systemctl list-units --all 'walter-memory*' --no-legend
systemctl show -p ExecStart --value walter-memory-pipeline.service
```

In the observed deployment, the bus pipeline loaded triage; restart it after source changes and check it is active:

```bash
systemctl restart walter-memory-pipeline.service
systemctl is-active walter-memory-pipeline.service
systemctl start memory-autopilot
walter-memory health
```

Read the newly completed autopilot result at `/root/.hermes/logs/memory-autopilot/latest.json`; verify freshness rather than trusting an older score.

Check new decisions and model-call timestamps:

```sql
SELECT rule, count(*), max(decided_at)
FROM triage.decisions
WHERE rule LIKE 'silent group%'
GROUP BY rule;

SELECT max(at)
FROM system.model_calls
WHERE processor = 'triage';
```

Require an eligible new event before claiming live savings. No new Line decision means live verification is pending, even if tests and historical replay pass. Append the policy, evidence, and validation limits to `/walter/docs/DECISIONS.md`.
