# AA Intelligence Index — API v2 vs Recharts Discrepancy

**Critical pitfall verified 2026-07-29.**

The Artificial Analysis API v2 endpoint (`/api/v2/data/llms/models`) and the
Recharts DOM graph ("Intelligence vs Cost per Task") return **different
intelligence scores** for the same model.

## Root cause

The API v2 returns the **non-reasoning** (base) variant's score by default.
The Recharts graph on model pages shows the **reasoning** variant's score
(with thinking/reasoning enabled). The gap is 15–25 points.

## Examples

| Model | API v2 (base) | Recharts (max) | Gap |
|---|---|---|---|
| GPT-5.6 Luna | 26.6 | 51.2 | **+24.6** |
| GPT-5.6 Sol | 57.7 | 58.9 | +1.2 |
| DeepSeek V4 Pro | 31.2 | 44.3 | **+13.1** |
| Claude Opus 5 | 55.7 | 60.7 | +5.0 |

## Impact

Using API v2 scores for Pareto analysis understates model intelligence by
15-25 points for reasoning-enabled models. This can cause:
- Wrong model routed for reasoning tasks (underestimating capable models)
- Incorrect Pareto frontier (some models appear worse than they are)
- Bad cost/intelligence tradeoffs

## Rule

**Always prefer Recharts DOM scores for the actual reasoning variant you'll use.**
The API v2 is reliable only for:
- Non-reasoning model scores (GPT-5.6 Sol base where gap is small)
- Pricing data (accurate)
- Benchmark scores (GPQA, HLE, etc. — these are the same regardless)

When computing Pareto frontiers, use the `aa-intel-vs-cost-scraper` DOM scrape
method to get Recharts data (`cost_per_task` + reasoning intel), not the API v2.
