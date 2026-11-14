# aa-pareto-model-optimizer — Pareto policy and thresholds.

Moved verbatim from SKILL.md on 2026-11-01.

## Pareto policy

Compute the Intelligence surface only:

```text
frontiers.intelligence_aa:
  maximize intelligence_index
  minimize aa_cost_per_task_intelligence_usd
```

### 1. `strict_frontier`

All mathematically non-dominated rows:

```text
A dominates B when:
A.score >= B.score
AND A.cost <= B.cost
AND at least one inequality is strict
```

This remains the reference frontier.

### 2. `supported_frontier`

Upper concave envelope of score versus natural-log cost. These are globally supported trade-offs under a proportional-cost utility. This view is useful mathematically but may be too aggressive for practical tier discovery.

### 3. `upgrade_ladder` — primary decision view

Pareto optimality alone cannot decide whether a score gain justifies a price increase without an explicit utility policy. Use a transparent marginal-return policy:

1. choose the strongest knee on the global `supported_frontier` as the `value_anchor`;
2. keep strict-frontier rows above that anchor in ascending raw AA task cost;
3. compute each incremental return as `delta score / delta task cost`;
4. build the upper concave envelope by removing every interior row where marginal return rises toward the next model instead of diminishing;
5. retain the maximum-score endpoint as `quality_ceiling`.

The retained sequence has monotonically decreasing marginal score gained per additional dollar. This is the set of discrete models that can be optimal for some linear willingness to pay for benchmark score. There is no fixed 5% performance band and no configurable score-spacing threshold in this decision layer.

Each tier reports:

```text
actual_uplift_pct_from_anchor
score_gain_from_anchor
cost_multiple_from_anchor
previous_tier
score_gain_from_previous_tier
cost_increase_from_previous_tier_usd
marginal_score_per_dollar_from_previous
incremental_cost_per_score_point
marginal_return_retained_vs_previous_segment_pct
```

Use `incremental_cost_per_score_point` as the break-even interpretation: advance to that tier only when one extra Index point is worth at least that many dollars per benchmark task. `removed_by_marginal_return` preserves every omitted row plus its previous/next models and incoming, outgoing, and bypass marginal returns.

A point such as GLM-5.2 or GPT-5.6 Sol xhigh may remain mathematically non-dominated yet be removed from the upgrade ladder when a later model offers a more efficient incremental upgrade. Never delete it from `strict_frontier`.

`quality_ceiling` remains visible because maximum quality can be rational when cost has near-zero weight, even if its final marginal return is poor.

### 4. `pragmatic_frontier` — value-filtered report view

Build this view for the Intelligence axis only; modality metrics are handled in their separate task datasets:

1. start from `epsilon_frontier`;
2. remove score steps below `minimum_gain` (default `0.5` Index points) compared with the last retained candidate;
3. walk candidates from cheapest to most expensive, comparing each with the last retained candidate;
4. remove a candidate when its incremental AA benchmark-task cost exceeds `max_incremental_cost_per_score_point` (default `$0.75` per additional Index point); after a removal, compare the next candidate against the last retained one.

This absolute marginal-cost cap is a practical value filter, not part of strict Pareto mathematics. A point can remain in `strict_frontier` and be removed from `pragmatic_frontier`; inspect `removed_by_cost_inefficiency` for the rejected model, comparison model, incremental cost, and threshold. The `quality_ceiling` stays separately visible in `upgrade_ladder` even when it exceeds the practical cap.

### 5. `standout_frontier` — local diagnostic only

Compare each interior strict-frontier point with its immediate cheaper and dearer neighbors. Keep endpoints and local knees whose incoming/outgoing marginal score-per-log-cost ratio reaches `--min-knee-strength` (default `2.0`).

Use this view to explain local geometry, never as the normal recommendation shortlist. Immediate-neighbor artifacts can make a globally redundant model look exceptional.

### Compatibility views

`epsilon_frontier` and `pragmatic_frontier` remain available in schema version 10. `strict_frontier` remains the mathematical audit view; use the `pragmatic_frontier` for the value-filtered report table and `upgrade_ladder` for normal recommendations.

## Thresholds

Defaults:

```text
Intelligence Index > 35
minimum knee strength = 2.0 (diagnostic only)
maximum marginal AA task cost = $0.75 per additional Index point
```

The upgrade ladder has no score-step threshold. Override the practical frontier's value cap, eligibility, or diagnostic knee when needed:

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/refresh.py \
  --min-intel 45 \
  --min-gain 0.5 \
  --min-knee-strength 2.5 \
  --max-incremental-cost-per-score-point 0.75
```

AA-only is the default. `--with-kie` is the optional live Kie.ai stage. When enabled, `refresh.py` reads the public pricing-table API (`https://api.kie.ai/client/v1/model-pricing/page`) and groups its per-direction records (Input, Cached Input, Cache Writes, Output) by model family before falling back to model-page HTML. A model page showing a placeholder such as `wocx` is not evidence that pricing is absent: verify the pricing-table API first. Kie translated costs remain estimates obtained from the Kie/AA blended token-price ratio and must be reported separately from the AA frontier.

