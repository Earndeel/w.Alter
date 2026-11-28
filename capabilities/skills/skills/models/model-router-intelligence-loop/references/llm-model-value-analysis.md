---
name: llm-model-value-analysis
description: Analyze LLM model value by combining benchmark quality, real usage cost, speed, context, and workload fit. Use when the user asks to “check” a model, compare models, choose a provider/model, or assess intelligence/cost ratios.
---

# LLM Model Value Analysis

## When to use

Use this skill when Monsieur asks to check, compare, rank, or choose LLMs by quality, cost, benchmarks, speed, context, or practical workload fit.

Trigger phrases include:

- “check this model” / “checker [model]”
- “is [model] good?”
- “best model for coding/design/agents/research”
- “ratio intelligence/cost”
- “real usage cost”
- “benchmark by usage”

## Core rule

Do **not** answer a model check with only a headline ranking. A proper check must produce a cost-adjusted and workload-specific analysis. The user corrected a shallow answer on GLM-5.2; treat that as the standard failure mode to avoid.

## Workflow

1. **Resolve the exact model identity.**
   - Distinguish aliases, provider variants, max/turbo/thinking/non-thinking versions, context sizes, and quantized/self-hosted variants.
   - If a specific model ID will be used operationally, load the model-ID lookup procedure first.

2. **Collect raw benchmark and pricing data.**
   - Prefer Artificial Analysis for Intelligence Index, cost-per-task, blended price, output speed, and context.
   - Cross-check with official model pages, provider pricing pages, OpenRouter-style catalogs, Design Arena, coding leaderboards, and agent/tool-use benchmarks where relevant.

3. **Compute derived value metrics.**
   - `intelligence_per_dollar = Intelligence Index / cost_per_AA_task`
   - `relative_cost_vs_baseline = model_cost / baseline_cost`
   - `quality_delta_per_extra_dollar = (model_score - baseline_score) / (model_cost - baseline_cost)` when comparing upgrades.
   - Use terminal or code for arithmetic; do not calculate mentally.

4. **Segment by workload.**
   Analyze separately for:
   - general reasoning / knowledge;
   - coding;
   - frontend/design;
   - long context / document analysis;
   - agentic tool use;
   - extraction/compression at scale;
   - latency-sensitive chat.

5. **State gaps explicitly.**
   Dynamic benchmark pages can omit or hide tables. If a score was not cleanly extracted, say so and avoid pretending precision.

## Output format

Preferred structure:

1. **Verdict court** — one clear sentence.
2. **Raw data table** — benchmark, price, speed, context.
3. **Ratio table** — model, score, cost, score-per-dollar, practical interpretation.
4. **Usage matrix** — best/acceptable/avoid by workload.
5. **Recommendation** — what to test first and what baseline to compare against.
6. **Sources / caveats** — plain URLs, no markdown links if replying to Monsieur.

## Pitfalls

- Do not treat “#1 on a leaderboard” as a purchasing recommendation without cost-per-task.
- Do not conflate benchmark quality with tool-calling reliability; agent/tool use needs its own evidence.
- Do not assume one provider’s hosted variant behaves like another provider’s or self-hosted weights.
- Do not silently substitute a nearby model version.
- Do not use one-off hype articles as the only source; cross-check with benchmark pages or official pricing.

## Reference snapshots

- `references/glm-5-2-analysis-snapshot-2026-06.md` — GLM-5.2 value-analysis snapshot and user-facing lesson from the correction that created this skill.
