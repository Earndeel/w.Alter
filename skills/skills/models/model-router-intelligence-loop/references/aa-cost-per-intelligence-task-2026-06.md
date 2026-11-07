# Artificial Analysis — Cost per Intelligence Index Task

Session lesson: when building W.Alter/Hermes model-router intelligence, do not stop at raw benchmark scores or input/output pricing. Monsieur explicitly flagged **Cost per Intelligence Index Task** from Artificial Analysis as a core routing indicator.

## Why it matters

This metric is task-level value density: it combines quality and cost into a direct routing signal. For W.Alter, it is more actionable than a standalone Intelligence Index or token price because routes are chosen by expected task value, not leaderboard aesthetics.

## Required ingestion behavior

For every Artificial Analysis candidate model, capture at minimum:

- `artificial_analysis_intelligence_index`
- `artificial_analysis_coding_index` when available
- task-relevant benchmark scores such as HLE, GPQA, TerminalBench, tau2 when available
- input/output pricing
- **`aa_cost_per_intelligence_index_task_usd`**
- source URL and raw payload/screenshot-derived row where possible

Store `aa_cost_per_intelligence_index_task_usd` as a benchmark/category like:

```txt
benchmark = aa_cost_per_intelligence_index_task_usd
category  = cost_efficiency
source    = artificial_analysis
unit      = usd_per_task, if the schema supports units
```

## Workflow correction

If paid tests are suspended because credits are exhausted, continue non-paid enrichment immediately and include this AA metric in the same research pass. Do not produce a router report until value-density metrics have been checked, or explicitly label them missing.

## Example interpretation from the session

The metric changed the ranking materially:

- MiMo V2.5 Pro had the best AA cost/intelligence task value, but remained experimental because the OpenRouter endpoint previously returned unusable/null content.
- DeepSeek V4 Pro remained the best routable low-cost candidate because its endpoint behavior was more reliable.
- Claude Fable 5 looked excellent on quality, but premium/expensive on this value-density metric.

The lesson is endpoint reliability and cost-per-intelligence must both be present in the decision matrix; either alone misleads.