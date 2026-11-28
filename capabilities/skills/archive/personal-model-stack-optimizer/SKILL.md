---
name: personal-model-stack-optimizer
description: Pick Monsieur's optimal model stack for his providers.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [pareto, llm, model-selection, cost, benchmarking]
    related_skills: [aa-pareto-model-optimizer, aa-intel-vs-cost-scraper, model-id-lookup]
---

# Personal Model Stack Optimizer

## Overview

Build Monsieur's optimal model stack by combining:
1. Live AA Pareto data (Intelligence Index + Agentic Index)
2. Our real benchmark results (speed, tool-use success, streaming)
3. Provider constraints (Codex blocks GPT-5.6, Kie.ai no streaming)
4. Actual costs from our providers (Kie.ai discounts, OpenRouter pricing)

The output is a **ranked shortlist of 4 models to keep**, not just a mathematical frontier.

## Provider Stack

| Provider | Models available | Pricing | Notes |
|---|---|---|---|
| **OpenRouter** | DeepSeek V4 Pro/Flash, GPT-5.6 Luna/Sol (API price) | pay-per-use | Streaming OK, fast |
| **Kie.ai (Claude)** | claude-opus-5, claude-opus-4-8, claude-sonnet-5, claude-fable-5 | −72% vs API | No streaming, slow (~4×), Bearer auth |
| **Kie.ai (GPT)** | gpt-5-6-luna, gpt-5-6-sol | −72% vs API | Responses API, tool-use OK, slow |
| **Codex** | GPT-5.5 only (GPT-5.6 BLOCKED) | $20/mo flat | App interactive only |

## Workflow

### 1. Extract both AA indexes live

Get Intelligence Index from the Recharts graph (see `aa-intel-vs-cost-scraper`).
Get Agentic Index from `https://artificialanalysis.ai/models/capabilities/agentic` — see `references/agentic-index-extraction.md` for the Next.js RSC extraction technique.

Always extract BOTH — they rank models differently. Agentic Index penalizes weak tool-use models.

### 2. Run Pareto with pragmatic filters

```
python3 scripts/pareto.py data.json \
  --intel-field y --cost-field x \
  --min-intel 40 --min-gain 0.5
```

For Agentic Index, lower threshold (scores compress ~5-9 pts):
```
python3 scripts/pareto.py agentic.json \
  --intel-field agentic_index --cost-field cost_per_task_usd \
  --min-intel 30 --min-gain 0.5
```

### 3. Filter through providers

Keep only models available on Monsieur's stack. Annotate: provider, real cost/session, streaming, tool-use support.

### 4. Identify standout models

- **Sauts rentables**: +2.5 pts for <2× price
- **Leaders par gamme**: best per price bracket
- **Sweet spots**: where next upgrade costs disproportionately more

### 5. Propose 4 models

1. Daily driver (90% volume)
2. Tool-use specialist
3. Complex task handler
4. Maximum quality (critical/client)

Always justify exclusions.

## Key Findings (July 2026)

- **DeepSeek V4 Pro (max)**: daily driver, 36.4 agentic, $0.046/task, 788 A/$
- **GPT-5.6 Luna (xhigh)**: GPT sweet spot — max only +2.7 pts for +50% cost
- **Claude Opus 5**: dominates Sol at every tier
- **Sol never wins**: Opus 5 beats it on Intel, Luna beats it on Agentic
- **Codex irrelevant**: GPT-5.6 blocked

## Pitfalls

1. **Confusing Intel Index with Agentic Index.** Agentic is 5-9 pts lower; changes rankings. Always state which.
2. **Mentioning irrelevant models.** No Gemini, Grok, Kimi unless asked. Stack = Codex + Kie.ai + OpenRouter.
3. **Using stale AA scores.** Always fetch live. Scale shifts, prices change.
4. **Forgetting Kie.ai speed.** ~4× slower, no streaming. Matters for interactive use.
5. **Thinking Codex serves GPT-5.6.** It's blocked. ChatGPT app only.
6. **OpenRouter IDs use dots:** `openai/gpt-5.6-luna` works, `gpt-5-6-luna` fails.

## Verification

- [ ] Both AA indexes fetched live
- [ ] Pareto with explicit --min-intel and --min-gain
- [ ] All models available on Monsieur's providers
- [ ] Exclusions documented
- [ ] Provider constraints noted
- [ ] Date and thresholds reported

## References

- `references/agentic-index-extraction.md` — Next.js RSC extraction technique for the AA Agentic Index page
- `references/intel-vs-agentic-delta.md` — Score deltas between Intelligence Index and Agentic Index, and how they change rankings
