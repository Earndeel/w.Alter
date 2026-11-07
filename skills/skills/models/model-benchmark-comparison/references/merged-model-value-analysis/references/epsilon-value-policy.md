# Epsilon dominance versus economic shortlist

## Core distinction

The strict Pareto frontier answers: which rows are not simultaneously worse on
score and cost? It is not a buying recommendation.

Near-price epsilon dominance answers a narrower question:

```text
B removes A when:
B.score - A.score >= epsilon_score_gain
AND B.cost <= A.cost * (1 + epsilon_cost_premium_pct / 100)
```

This catches a cheaper row made pointless by a slightly more expensive, better
row. It does **not** catch an expensive quality tier whose score gain is small
relative to its price. Never call `epsilon_frontier` a complete cost-benefit
shortlist without a separate diminishing-returns check.

## Three reporting layers

1. `strict_frontier`: mathematical reference; retain every non-dominated quality
   tier.
2. `epsilon_frontier`: remove near-price inferior rows using explicit score and
   cost tolerances.
3. `value_frontier` or recommendation layer: optionally remove large cost cliffs
   with weak relative score gains. If the collector does not calculate this
   layer, say so instead of implying that `pragmatic_frontier` has done it.

The existing adjacent `min_gain` filter is only a score-step filter. It is not a
cost/quality efficiency rule.

## Diagnostic procedure

For every adjacent pair in both Intelligence and Agentic tables, calculate:

- absolute score gain;
- relative score gain;
- absolute cost delta per task;
- relative cost premium;
- score-per-dollar change;
- whether epsilon catches the lower row;
- whether a separate value policy would classify the higher row as `quality-only`.

Report why each retained or removed row changed status. Distinguish strict
removal, epsilon removal, min-gain removal, and value-policy presentation.

## Calibration example from a live AA snapshot

| Model | Intelligence | AA cost/task |
|---|---:|---:|
| DeepSeek V4 Flash max | 40.28 | $0.0234 |
| DeepSeek V4 Flash 0731 max | 49.93 | $0.0271 |
| GPT-5.6 Luna max | 51.24 | $0.0658 |

Flash 0731 gained `9.65` points for a `16.1%` premium. A `10%` epsilon keeps
the older Flash row, even though a user may reasonably call 16% "a little more
expensive"; a `20%` epsilon would remove it.

Luna max gained only `1.31` points (`2.62%`) over Flash 0731 for a `142.4%`
premium. It correctly remains on the strict frontier because it is slightly
better, but near-price epsilon cannot remove it: the price gap is far outside
epsilon. Its score-per-dollar falls from roughly `1,840` to `779`, so it should
be labelled a quality-only tier or removed from a cost-first value shortlist if
that separate policy is adopted.

These values are diagnostic evidence, not a permanent threshold choice. Any
adopted threshold must be written into the snapshot policy and reported.

## Missing-model diagnostic

Do not say a model is absent because it is missing from a compact table. Check:

1. `data[]` — AA supplied the row;
2. `strict_frontier` — strict dominance removed it;
3. `removed_by_epsilon` — near-price epsilon removed it;
4. `removed_by_min_gain` — adjacent score filter removed it;
5. value-policy output — it was intentionally excluded from a cost-first view.

A DeepSeek V4 Pro row may exist in `data[]` while being absent from the
Intelligence strict frontier because a newer Flash variant has both a higher
score and a lower task cost.
