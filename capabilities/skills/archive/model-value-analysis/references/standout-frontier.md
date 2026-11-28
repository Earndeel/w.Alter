# Marginal Upgrade Ladder and Standout Diagnostics

## Why this layer exists

A strict Pareto frontier is an audit set, not a recommendation ladder. Fixed score bands create boundary artifacts: a model can survive by barely crossing a threshold even when the next model buys substantially more score per incremental dollar.

The primary decision view is therefore `upgrade_ladder`. `standout_frontier` remains a local-neighbor geometry diagnostic only.

## Deterministic marginal contract

Run independently for Intelligence and Agentic with the matching AA task-cost field:

1. Build the strict Pareto frontier and sort it by increasing raw task cost.
2. Select the strongest knee on the global log-cost `supported_frontier` as `value_anchor`.
3. Keep the anchor and every strict-frontier row above it.
4. For adjacent rows, calculate `marginal return = delta score / delta task cost`.
5. Build the upper concave envelope with a monotone stack. Remove an interior row whenever its incoming marginal return is less than or equal to its outgoing marginal return.
6. Continue until retained marginal returns decrease strictly from the anchor to the maximum-score endpoint.

No fixed score-gain percentage is used. The maximum-score endpoint remains visible as `quality_ceiling` because it can be rational when cost has near-zero weight.

## Decision interpretation

Each retained transition reports:

- `marginal_score_per_dollar_from_previous`;
- `incremental_cost_per_score_point`, its inverse;
- `marginal_return_retained_vs_previous_segment_pct`.

The inverse is the useful break-even rule: buy the next tier only when one extra benchmark Index point is worth at least that many dollars per task. Every retained point can be optimal for some linear score-versus-dollar utility.

Every omitted strict-Pareto row remains in `removed_by_marginal_return`. Its `previous_model` and `next_model` must be the final retained neighbors, not temporary stack points. The artifact records incoming, outgoing, and bypass marginal returns.

## Intelligence calibration — live 2026-07-31 snapshot

| Tier | Index | AA $/task | Marginal score/$ | Incremental $/point |
|---|---:|---:|---:|---:|
| DeepSeek V4 Flash 0731 max | 49.93 | 0.0271 | anchor | anchor |
| Grok 4.5 high | 53.83 | 0.4410 | 9.422 | 0.1061 |
| Claude Opus 5 medium | 56.28 | 0.7224 | 8.719 | 0.1147 |
| Kimi K3 max | 57.11 | 0.8552 | 6.264 | 0.1596 |
| Claude Opus 5 high | 58.86 | 1.2259 | 4.726 | 0.2116 |
| Claude Opus 5 xhigh | 60.07 | 1.8021 | 2.090 | 0.4785 |
| Claude Opus 5 max | 60.69 | 2.3365 | 1.167 | 0.8568 |

Two diagnostic removals explain the policy:

- **GLM-5.2 max:** 4.362 score/$ from Flash 0731 into GLM, then 18.478 score/$ from GLM into Grok. The return rises, so GLM lies below the retained Flash→Grok chord.
- **GPT-5.6 Sol xhigh:** 1.736 score/$ from Kimi into Sol, then 20.580 score/$ from Sol into Opus high. Sol is a threshold artifact, not an efficient marginal tier.

## Agentic calibration — live 2026-07-31 snapshot

The same independent calculation retains:

```text
DeepSeek V4 Flash 0731 max
→ Claude Opus 5 high
→ Claude Opus 5 xhigh
→ Claude Opus 5 max
```

Kimi K3 max remains in the Agentic strict frontier but is omitted from the marginal ladder because Opus 5 high offers a higher raw incremental return from the final retained anchor. This does not make Kimi dominated; it means Kimi is not optimal under this linear score-per-task-dollar utility.

## Role of `standout_frontier`

`standout_frontier` compares immediate strict-frontier neighbors in log-cost space and can reveal sharp local knees. It must not drive the normal shortlist: a locally sharp point may still be globally bypassed by a later model with better raw marginal return.

## Pitfalls

- Never overwrite or shrink `strict_frontier`; the ladder is a decision view.
- Never mix Intelligence scores with Agentic task costs, or vice versa.
- Never use global `Index / cost` as a substitute for incremental `delta Index / delta cost`; they answer different questions.
- Never reintroduce a fixed 5% score band into `upgrade_ladder`.
- Display rounding occurs only after hull comparisons.
