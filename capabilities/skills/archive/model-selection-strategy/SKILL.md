---
name: model-selection-strategy
description: Use when choosing which LLM to use. Pareto routing strategy.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [model-selection, pareto, routing, cost-optimization, agentic]
    related_skills: [aa-pareto-model-optimizer, aa-intel-vs-cost-scraper, model-value-analysis]
---

# Model Selection Strategy

Which model to use for which task, based on live AA data crossed with our providers: OpenRouter, Kie.ai, Codex.

The Pareto frontier is computed by `aa-pareto-model-optimizer`. This skill is the **decision layer** — takes Pareto data and maps it to our infrastructure.

## Provider Capabilities

| Provider | Models available | Streaming | Tool-use | Pricing |
|---|---|---|---|---|
| **OpenRouter** | DeepSeek V4 Pro/Flash, GPT-5.6 Luna/Sol (API price) | ✓ | ✓ Chat Completions | Pay per token |
| **Kie.ai** | GPT-5.6 Luna/Sol/Terra, Claude Opus 5, Sonnet 5 | ✗ | ✓ Responses API | −60-72% vs API |
| **Codex** | GPT-5.5 and below only | ✓ | ✓ Responses | Forfait $20/mo |

⚠️ Codex blocks all GPT-5.6: `not supported when using Codex with a ChatGPT account`.

## 4-Model Framework (Agentic Index, July 2026)

### Tier 1 — Daily Driver
**DeepSeek V4 Pro (max)** via OpenRouter
- Agentic: 36.4 · $0.046/task · A/$: 788 · 90% of volume.

### Tier 2 — Entry Mid-Range
**GPT-5.6 Luna (high)** via Kie.ai
- Agentic: 40.1 · $0.25/task · +3.7 pts vs DeepSeek.

### Tier 3 — GPT Sweet Spot
**GPT-5.6 Luna (xhigh)** via Kie.ai
- Agentic: 42.9 · $0.39/task · +2.8 pts for 1.6× price. Best Luna tier.

### Tier 4 — Premium
**Claude Opus 5 (high)** via Kie.ai
- Agentic: 52.1 · $2.26/task · For critical tasks only.

## Why Sol was removed

Under Agentic Index, Sol is dominated at every tier:
- Sol (medium) 44.5 @ $1.19 — Luna (xhigh) costs 3× less for −1.6 pts
- Sol (xhigh) 51.8 @ $2.71 — Opus 5 (high) costs less, scores higher
- Sol (max) 54.0 @ $4.19 — Opus 5 (xhigh) costs less, scores higher

Sol was viable under Intelligence Index, not under Agentic.

## Metric choice

| Metric | Use for | Key difference |
|---|---|---|
| **Agentic Index** | Tool-use, planning, autonomy | More discriminating; DeepSeek −7.9 pts |
| **Intelligence Index** | General reasoning, writing | Higher scores, broader coverage |

Default to Agentic Index. Fall back to Intelligence Index for pure reasoning.

## Routing decision tree

```
Task?
├─ High volume (code, search, files) → DeepSeek V4 Pro (OpenRouter)
├─ GPT-5.6 tool-use (Responses API)  → Luna high/xhigh (Kie.ai)
├─ Complex multi-step reasoning      → Luna xhigh/max (Kie.ai)
└─ Critical, DeepSeek+Luna fail      → Opus 5 high (Kie.ai)
```

## Pitfalls

1. **Codex not for inference.** GPT-5.6 blocked. Interactive ChatGPT use only.
2. **OpenRouter model naming.** `openai/gpt-5.6-luna` uses **dots** (5.6), not dashes (5-6). Models endpoint returns dashed form; API requires dots.
3. **Kie.ai tool-use format.** Responses API format (`type: function_call` / `function_call_output`), not Chat Completions. Hermes handles via `kie-gpt` provider.
4. **AA data is live.** Scores/prices change. Re-scrape before threshold-dependent decisions.
5. **Kie.ai latency.** 2-4× slower than OpenRouter (Java proxy queue). OK for background, painful for interactive.
6. **Agentic Index penalizes non-agentic models.** DeepSeek V4 Pro drops 7.9 pts vs Intelligence Index — this is normal, not a quality issue. It excels at throughput tasks.

## Verification

After routing changes:
- [ ] Provider configured: `hermes --provider <name>`
- [ ] Model available: `hermes -z "OK" --provider X --model Y`
- [ ] Tool-use works (test forced tool call)
- [ ] Cost matches expectation (check after real session)
