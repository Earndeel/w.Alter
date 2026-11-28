# Adjacent Pareto Ratio Filter

## Trigger

Use this reference when a Pareto result contains a strict frontier plus a pragmatic shortlist, and the user asks whether a small `min_gain` filter really reflects cost/quality efficiency.

## Definitions

Keep these metrics separate:

- **Global ratio:** `index / aa_cost_per_task`. This is the user's usual Index/$ value for a row.
- **Marginal ratio:** `(next_index - previous_index) / (next_cost - previous_cost)`. This measures the efficiency of the incremental upgrade and can disagree with the global ratio.
- **Strict frontier:** maximize the selected Index and minimize the matching AA task cost; no presentation filter is applied.
- **Pragmatic efficiency tiers:** a presentation layer only. It may collapse adjacent near-ties, but must preserve the strict frontier and identify rows classified as quality upgrades.

The task-cost axis must match the Index: Intelligence uses `aa_cost_per_task_intelligence_usd`; Agentic uses `aa_cost_per_task_agentic_usd`.

## User-corrected pitfall

The legacy implementation in `refresh.py` and `pareto.py` compares only an absolute score jump:

```text
next_index - previous_retained_index < min_gain
```

That is an Index-spacing filter, not a ratio-significance filter. Do not claim that `min_gain: 0.5` measures whether the next model is materially better value.

## Recommended decision contract

1. Compute and retain the strict frontier first.
2. Sort rows by increasing task cost.
3. For a ratio-based shortlist, compare adjacent rows with the selected global ratio and an explicit relative threshold, e.g. `min_ratio_delta_pct: 5`.
4. If the ratio change is below the threshold, label the next row a near-tie efficiency point; do not erase it from the strict frontier. It can remain in a quality-oriented view.
5. Report which ratio was used. If the user cares about the value of the upgrade itself, also show the marginal ratio rather than silently substituting it.
6. Never mix this filter with Kie pricing unless explicitly requested: the AA frontier remains the benchmark comparison, while Kie is an annotation with an estimated axis-matched task cost.

The threshold is a policy parameter, not a fact in the data. Five percent is a reasonable starting point for a readable shortlist; use a different value only when the user's tolerance for near-ties is known.

## Reproduction example

Current Agentic values from the AA snapshot:

| Model | Agentic | AA $/task | Global A/$ |
|---|---:|---:|---:|
| DeepSeek V4 Pro max | 36.36 | 0.0462 | 787.86 |
| GPT-5.6 Luna high | 40.07 | 0.0503 | 796.18 |

Luna gains `3.71` Agentic points for `+$0.0042` per task. Its global ratio is only about `+1.06%` higher, while the score is about `+10.20%` higher and the task cost about `+9.05%` higher. Under a 5% global-ratio threshold, Luna is a quality tier rather than a new efficiency tier; both remain non-dominated on the strict frontier.

## Reporting language

Prefer:

> « Luna high est un upgrade de qualité, pas un nouveau palier de rentabilité : son ratio global n'est supérieur que de 1,06 %. »

Avoid:

> « Luna a été supprimée »

unless the report explicitly says it was removed only from the pragmatic presentation view and links it to the retained strict frontier.
