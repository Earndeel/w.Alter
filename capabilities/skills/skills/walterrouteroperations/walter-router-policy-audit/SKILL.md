---
name: walter-router-policy-audit
description: Use when auditing Walter Router tier rules, quota-spent fallbacks, subscription economics, or specialist routes on Monsieur's VM.
---

## 1. Capture policy and live selections

Run from the Router checkout:

```sh
cd /walter/cognition/router
walter-router plans list
walter-router plans consumption
walter-router dossier general
for level in L1 L2 L3; do
  printf '\n== %s ==\n' "$level"
  walter-router pick general --level "$level"
done
```

Use `plans list`, not bare `plans`, which requires a subcommand. Record when you checked and distinguish the supplied index snapshot from later live reads. Use Monsieur's `tier_rules` as the policy baseline. Capture complete `pick` output before narrowing it: the selected model and provider are not the whole execution chain. Inspect the `execution` entries, especially `provider` and `access`. Keep stderr separate when parsing JSON.

## 2. Trace declared fallbacks into runtime execution

```sh
cd /walter/cognition/router
grep -nE 'when_quota_spent|^def ' analysis/knowledge.py analysis/select.py analysis/tiers.py
grep -rnE 'quota_switch|quota_spent|cost_source|KIE_MAX_PREMIUM|KIE_CODEX_MODELS' --include='*.py' serve analysis
```

Read `analysis/knowledge.py` for the declared levels and replans, `analysis/select.py` and `analysis/tiers.py` for candidate construction and eligibility, and `serve/routes.py` and `serve/execution.py` for the actual quota switch and route ordering. Evaluate each tier both normally and with its subscription spent, without forcing a live quota change. Verify that its `when_quota_spent` model and ordinary `fallback` have a usable route in the relevant state; a catalog offer alone does not establish executability. Check score ordering (`L1 < L2 < L3` where required), provider separation, and any marginal-gain or cost rules using comparable benchmark variants from the same snapshot. Use `general_points` to investigate the points behind the tier calculation, not to override the tier rules.

## 3. Check quota telemetry and the cost basis

Use the checkout's Python environment and Router DB connector. Inspect schema before projecting columns: `models.latest_subscription_costs` did not expose `route_provider`, and `models.subscription_usage` uses `read_at`, not `at`.

```sh
cd /walter/cognition/router
venv/bin/python - <<'PY'
from walter_router.store import db

with db.connect() as c:
    for table in ('latest_subscription_costs', 'subscription_usage'):
        cols = c.execute('''
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'models' AND table_name = %s
            ORDER BY ordinal_position
        ''', (table,)).fetchall()
        print(table, [r['column_name'] for r in cols])
    for r in c.execute('''
        SELECT sub_id, window_name, source, estimated, count(*) AS n,
               min(read_at) AS first_read, max(read_at) AS last_read,
               max(used_percent) AS peak_used_percent
        FROM models.subscription_usage
        WHERE read_at > now() - interval '8 days'
        GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4
    '''):
        print(dict(r))
PY
```

The eight-day summary checks freshness and coverage; its peak is not current usage. Check the latest reading and `resets_at` for the window the runtime actually tests. Keep calibration and estimated readings separate from observed usage. Inspect the cost view's `detail.models` if present, and trace a quoted `pace` price through `serve/execution.py` before comparing it with a full-quota estimate or a metered fallback. Don't assume the nominal subscription price describes the cost after the switch.

## 4. Verify offers and specialist routes

Use `walter_router.analysis.select.latest_snapshots(c)` with `load_offers(c, snaps)` to inspect candidate offers from one snapshot, then cross-check them against the runtime route list or eligibility code. For a specialist, run `walter-router pick <task>` (for example, `decision_vision`, `tts`, `document`, or `engineering`) and verify task compatibility as well as route availability. If a task's consumer is unclear, search the Router checkout and then relevant repositories under `/walter`; don't search `/` recursively, which was interrupted before producing useful evidence.

Report each issue with the declared policy, observed selection and route, affected quota state, and the specific rule or cost consequence. Label inferred behavior separately from verified runtime behavior. Keep the audit read-only unless changes are explicitly authorized.
