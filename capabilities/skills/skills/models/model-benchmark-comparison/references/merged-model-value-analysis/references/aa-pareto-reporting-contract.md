# AA Pareto reporting contract

Use this contract whenever a live AA + Kie comparison is requested.

## Required output

Produce two separate tables, in this order:

1. `frontiers.intelligence_aa`: `intelligence_index` vs `aa_cost_per_task_intelligence_usd`.
2. `frontiers.agentic_aa`: `agentic_index` vs `aa_cost_per_task_agentic_usd`.

For every displayed row, show:

- model and index;
- the matching AA cost per benchmark task;
- `score_per_dollar` (index points per matching AA dollar/task);
- if Kie has exact verified input/output rates: the matching translated Kie cost/task and reduction versus the matching AA cost/task;
- Kie status and source when available.

Do not use the Intelligence task cost for Agentic, or vice versa. Do not replace task cost with blended $/M token pricing.

## Kie evidence

A Kie page can exist without exposing a usable rate. `verified_rates` requires exact input and output prices. `unverified`, `not_found`, and `fetch_error` stay visible; never fill them with a family average or a generic Claude/GPT discount.

The Kie per-task number is an estimate translated from the Kie/AA blended token-price ratio. It is a comparison aid, not a claim that Kie invoices the AA benchmark task directly.

## Frontier visibility

Keep both views in the JSON artifact:

- `strict_frontier`: all mathematically non-dominated rows;
- `epsilon_frontier`: strict frontier after epsilon-dominance;
- `pragmatic_frontier`: the decision shortlist after epsilon-dominance and the configured `min_gain` filter;
- `removed_by_epsilon`: rows removed by the epsilon rule;
- `removed_by_min_gain`: rows removed by the adjacent minimum-gain filter.

A row in either removal list is not missing data. Mention it when its Kie coverage or model identity is relevant; never silently present it as absent.

The default epsilon rule is: remove row A when another row B gains at least
`0.5` index point and costs no more than `10%` above A. Both epsilon values are
stored in the snapshot policy and must be reported with the frontier.

## Refresh contract

The daily refresh is deterministic and must run without an LLM (`no_agent=True`). Verify that the scheduler is enabled, uses the collector script, and has a successful last run. The snapshot timestamp and row counts belong in the report.
