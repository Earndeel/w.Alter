# DeepSeek V4 Pro Max vs Claude Sonnet 5 Max — July 2026

Dated evidence snapshot for executor-value decisions. Re-fetch all live fields before reuse.

## Identity and capabilities

- DeepSeek OpenRouter ID: `deepseek/deepseek-v4-pro`; maximum thinking is a reasoning-effort setting, not a separate ID.
- OpenRouter advertised 1,048,576-token context plus `tools`, `tool_choice`, `structured_outputs`, `reasoning`, and `reasoning_effort`.
- Claude Sonnet 5 was the already verified executor baseline in the Fable planner/executor pipeline; its custom Kie tariff was not exposed.

## Observed live data

| Metric | DeepSeek V4 Pro Max | Claude Sonnet 5 Max |
|---|---:|---:|
| Input / 1M | $0.435 | $2.00 public |
| Output / 1M | $0.87 | $10.00 public |
| Blended / 1M | $0.544 | $4.00 |
| AA cost per task | $0.04484 | $1.52543 |
| Intelligence | 44.3 | 53.4 |
| Coding | 59.4 | 71.5 |
| TerminalBench | 64.0% | 80.5% |
| TAU2 | 96.2% | unavailable in observed API row |
| GDPval-AA | Elo 1307, rank 30 | Elo 1608, rank 5 |

Derived: DeepSeek was 7.35× cheaper on blended price and 34.02× cheaper on AA cost per task. Applying public prices to a 38,984-prompt + 2,093-completion-token executor trace, without cache discounts, gave about $0.01878 vs $0.09890 (5.27×). This is not a measured Kie invoice.

## Interpretation

A strict external plan reduces the executor's planning burden, so DeepSeek is a credible budget-default candidate. However, the 301-point GDPval-AA gap indicates materially weaker long-horizon agentic reliability. Use a real A/B and route premium fallback on invalid reports, repeated tool failures, failed artifacts, or failed recovery. Measure cost per successful task.

## Sources

- `https://openrouter.ai/api/v1/models`
- `https://artificialanalysis.ai/api/v2/data/llms/models`
- `https://artificialanalysis.ai/models/deepseek-v4-pro`
- `https://artificialanalysis.ai/models/claude-sonnet-5`
- `https://artificialanalysis.ai/evaluations/gdpval-aa`
