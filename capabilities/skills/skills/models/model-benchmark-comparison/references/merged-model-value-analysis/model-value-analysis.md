---
name: model-benchmark-comparison
description: Determine which LLMs are really worth it by task type — cross-references cost_per_task, intelligence, coding, agentic, and reasoning benchmarks. Complements model-benchmark-comparison.
version: 1.6.0
author: W.Alter
metadata:
  hermes:
    tags: [mlops, benchmarks, model-selection, cost-optimization, value-analysis]
    related_skills: [model-benchmark-comparison, aa-pareto-model-optimizer, aa-pareto-model-optimizer]
---

# Model Value Analysis — "Which Models Are Worth It?"

When the user asks "which models are worth it" or "compare cost vs intelligence by task type", this skill defines the analysis framework. It complements `model-benchmark-comparison` (which focuses on finding replacements for specific workloads) by adding the value/cost-per-task dimension.

## Trigger

Load when the user asks:
- "Which models are worth it?"
- "Compare cost vs intelligence"
- "Best value models by task type"
- "Does model X justify its price?"
- Any comparative analysis where `AA benchmark cost_per_task` is explicitly the benchmark metric (never as a universal billing unit)

## Cost-unit discipline — tokens first, AA tasks separately

A `task` is not a universal billing unit. AA's `cost_per_task` is the cost of AA's own normalized benchmark workload; it is valid for comparing models on the same AA axis, but it does not describe the price of an arbitrary user request. Report it as `AA benchmark task cost`, never as a generic per-task invoice.

Use this order of evidence:

1. **API/Kie.ai billing:** actual input, output, cached-input, and cache-write tokens with their separate prices;
2. **subscription billing:** the provider's native credits/quota, converted to tokens only when the exchange rates are documented or measured;
3. **AA benchmark layer:** Intelligence/Agentic score plus AA's benchmark-specific task cost.

For a token-priced route:

```text
cost_usd = input_tokens / 1e6 * input_price
         + output_tokens / 1e6 * output_price
         + cached_input_terms + cache_write_terms
```

For a credit-priced subscription, preserve the native unit and derive only what the evidence supports:

```text
credits = input_tokens / 1e6 * credits_per_input_million
        + output_tokens / 1e6 * credits_per_output_million
        + cached_credit_terms
```

A mix such as `100k input + 20k output` is a named scenario, not a universal “task”. If the provider exposes only messages, tasks, or a rounded quota counter, do not invent a token conversion. An unchanged counter is not proof of zero cost; report the token-credit charge as `unmeasured` unless a first-party usage record or attributable before/after delta exists. Keep `$0 marginal inside quota`, full-fee allocation, and post-quota cost as separate views. See `references/token-credit-accounting.md` for the evidence gate and reporting schema.

## Prerequisites

1. **Load `model-benchmark-comparison`** — for the API workflow, evaluation catalog, and `aa_analysis.py` script when API-wide catalog data is needed.
2. **Load `aa-pareto-model-optimizer`** for the current merged Intelligence + Agentic + Kie.ai snapshot. Its deterministic `scripts/refresh.py` path avoids spending reasoning tokens re-scraping rows in the conversation.
3. **Load `aa-pareto-model-optimizer`** when debugging the Recharts cost-per-task extraction itself.
4. Get the AA API key from the vault only when the API path is required: `vault get artificialanalysis/api_key` (prefix `aa_mgBk...`). The public browser/RSC collector does not require the key.

For the reusable live data contract, Kie verification rules, and cron-safe refresh recipe, read
`references/live-aa-kie-refresh.md`. For the exact two-table output contract,
axis-matched Kie task-cost fields, and strict-versus-pragmatic frontier reporting,
read `references/aa-pareto-reporting-contract.md`. For adjacent global-ratio versus
marginal-ratio filtering and the near-tie reporting rule, read
`references/pareto-ratio-filter.md`. For epsilon-versus-value filtering, adjacent
cost cliffs, and the Flash-0731/Luna diagnostic, read
`references/epsilon-value-policy.md`. For conflicting Kie page claims versus exact published rates, read
`references/kie-pricing-conflicts.md`.
## Workflow

### 1. Fetch API data (intelligence, coding, evaluations)

Run `aa_analysis.py` from `model-benchmark-comparison`:
```bash
AA_KEY=$(vault get artificialanalysis/api_key) \
  python3 /root/.hermes/skills/mlops/model-benchmark-comparison/scripts/aa_analysis.py
```

This gives: intel, blended $/1M, speed, and category rankings for 538 models.

### 2. Fetch AA benchmark cost_per_task (secondary benchmark layer)

**The API's `price_1m_blended_3_to_1` is not interchangeable with AA's normalized benchmark cost.** Fetch this field to compare models on the AA axis only; keep actual token-vector pricing and native subscription credits as the primary economic evidence. Models may use different token counts within AA's benchmark workload, but those counts are not a universal user-task profile:
- GPT-5.6 Sol uses ~69k tokens/task (ratio ~0.07 of blended price)
- Grok 4.5 uses ~104k tokens/task (ratio ~0.10)
- Claude Opus 5 uses ~180k tokens/task (ratio ~0.18)
- Claude Fable 5 uses ~137k tokens/task (ratio ~0.14)

Claude models look expensive on $/1M AND expensive on tokens/task — double penalty.
GPT-5.6 is token-efficient. Grok 4.5 sits in between.

Use the Recharts scraper:
```bash
# In a venv with playwright:
python3 /root/.hermes/skills/aa-pareto-model-optimizer/scripts/extract_recharts.py gpt-5-5 > cost_data.json
```
(Any model slug works — the scatter chart is the same across all pages. `gpt-5-5` is a stable default.)

This returns the current chart subset with `{label, x: cost_per_task_USD, y: intel_index}`; the count is dynamic and must never be treated as a catalog snapshot. **The subset is not an absence oracle:** if a requested model/tier is missing from the global payload, do not set its Intelligence metric to null solely from that omission. Open the model's own AA page, explicitly activate `Intelligence vs. Cost per Task`, extract its Recharts payload, and verify the returned label, URL, tier, `x` cost, and `y` score before marking the model unavailable. Preserve reasoning tiers (`medium`, `high`, `xhigh`, `max`) separately; never join by base URL alone. See `references/intelligence-targeted-fallback.md` for the reproducible fallback and the Opus medium/Kimi near-tie case.

### 3. Merge and compute task-type rankings

Cross-reference the cost_per_task with API evaluations:

| Task Type | Primary Metric | Secondary | Key Models to Check |
|-----------|---------------|-----------|---------------------|
| Agentic | GDPval-AA Elo on real work tasks | TerminalBench + coding index + TAU2 | Claude Opus 5, GPT-5.6 Sol (max), Grok 4.5, DeepSeek V4 Pro |
| Coding | coding_index × 0.5 + LiveCodeBench × 0.25 + SciCode × 0.25 | Intel | Claude Opus 5, GPT-5.6 Sol, Grok 4.5, DeepSeek V4 Flash |
| Reasoning | (GPQA + HLE + MMLU-Pro) / 3 | Math | Claude Opus 5, GPT-5.6 Sol, Gemini 3.6 Flash |
| Extraction | IFBench × 0.5 + TAU2 × 0.3 + LCR × 0.2 | Intel | MiniMax-M3, GLM-5.2, GPT-5.6 Luna |
| Compression | Intel / cost_per_task (cost-first) | Speed | DeepSeek V4 Pro, GPT-5.6 Luna, DeepSeek V4 Flash |
| Math | math_index × 0.5 + GPQA × 0.3 + AIME × 0.2 | Intel | GPT-5.6 Sol, Claude Opus 5, Gemini 3.6 Flash |

### 4. Compute Pareto frontier

For live AA + Kie analysis, produce **two independent tables in this order**:

1. **Intelligence:** maximize `intelligence_index` and minimize
   `aa_cost_per_task_intelligence_usd`;
2. **Agentic:** maximize `agentic_index` and minimize
   `aa_cost_per_task_agentic_usd`.

The task-cost field must match the index in each table. Never rank Agentic with
the Intelligence task cost, or substitute blended $/M token pricing for either
benchmark cost. Each row should show the index, AA $/task, index-per-dollar ratio,
and—only when Kie has exact verified input/output rates—the translated Kie $/task
and reduction versus the same AA $/task. A Kie page with no exact rates is
`unverified`, not a license to apply a family-average discount.

Keep both the mathematical strict frontier and any pragmatic shortlist in the
artifact. The legacy absolute `min_gain` rule is **not** a ratio-significance
rule: it compares only `next_index - previous_retained_index`. Do not describe it
as a cost/quality efficiency filter.

For a ratio-based pragmatic view, compare adjacent strict-frontier rows using the
same axis-matched global ratio (`index / aa_cost_per_task`) and an explicit relative
threshold such as `min_ratio_delta_pct`. A row whose ratio changes by less than the
threshold is a near-tie efficiency point; it may be omitted from the pragmatic
efficiency tiers but must remain visible in the strict frontier or as a quality
upgrade. Preserve both rows when the user cares about absolute quality rather than
only efficiency. Never silently delete a model because of this presentation filter.

Distinguish this from the marginal ratio `(next_index - previous_index) /
(next_cost - previous_cost)`: the two metrics can give opposite recommendations.
Report which one was used. The near-price epsilon frontier is **not** a complete value frontier: it catches a better model within a small cost premium, but it does
not remove an expensive quality tier whose score gain is small relative to its
price. Keep four concepts separate in every report:

1. `strict_frontier`: all mathematically non-dominated quality tiers;
2. `epsilon_frontier`: near-price replacements under explicit score/cost tolerances;
3. `upgrade_ladder`: the primary value view, built from the raw-cost upper concave envelope above the strongest global supported knee;
4. `standout_frontier`: immediate-neighbor local knees used for geometric diagnosis only.

For the primary `upgrade_ladder`, sort the axis-matched strict frontier by raw task cost above the value anchor, calculate each segment as `(next_score - previous_score) / (next_cost - previous_cost)`, and remove every interior point that causes marginal return to increase toward the next model. Iterate until retained marginal returns decrease monotonically. This is equivalent to the upper concave envelope of score versus raw task cost and requires no fixed performance-step threshold.

Report both `marginal_score_per_dollar_from_previous` and its inverse, `incremental_cost_per_score_point`. The inverse is the break-even utility: advance to a model only when one extra benchmark Index point is worth at least that many dollars per task. Preserve every rejected strict-Pareto model under `removed_by_marginal_return` with its incoming, outgoing, and bypass returns; never silently delete it from `strict_frontier`.

Use `standout_frontier` only to diagnose local knees against immediate strict-frontier neighbors. A sharp local ratio can be globally redundant when a later model buys more score per incremental dollar; it must not drive the normal recommendation shortlist.

Apply the marginal envelope independently to Intelligence and Agentic, always using the matching AA task-cost field. A row missing the score or task cost for the selected axis is not comparable and must be excluded from that axis with an explicit missing-data status; never borrow an Agentic score/cost to populate an Intelligence frontier.

For the value shortlist, calculate absolute and relative score gain, absolute and
relative cost premium, and the score-per-dollar change for every adjacent pair.
If a quality tier has a large cost cliff and a weak relative score gain, label it
`quality-only` or remove it from the cost-first shortlist — but never silently
remove it from the strict frontier. Record the chosen thresholds in the snapshot
policy; do not smuggle a new value rule into `min_gain` or call epsilon alone
"economic optimization".

For the current Agentic example, DeepSeek V4 Pro max
(36.36 at $0.0462) versus Luna high (40.07 at $0.0503) differs by only about 1.06%
in global Index/$, despite Luna gaining 3.71 Index points. A 5% relative-ratio
threshold would classify Luna as a quality tier, not a new efficiency tier; it
would not remove Luna from the strict frontier. For an Intelligence example,
a model can gain only a few percent of score while costing over 100% more; that
is a value-policy case, not epsilon-dominance.

When reporting, lead with the two tables and their values. Avoid implementation
jargon such as “mapping” unless the model/page association affects evidence or
coverage. The deterministic daily refresh (`no_agent=True`) is part of the
analysis contract and must remain enabled.

```python
def is_pareto(m, others):
    return not any(o['intel'] >= m['intel'] and o['cost_per_task'] <= m['cost_per_task']
                   and (o['intel'] > m['intel'] or o['cost_per_task'] < m['cost_per_task'])
                   for o in others)
```

Historical example only (never current evidence without a fresh run): DeepSeek V4 Pro (max) → GPT-5.6 Luna (max) → Grok 4.5 (high) → GPT-5.6 Sol (high) → GPT-5.6 Sol (xhigh) → GPT-5.6 Sol (max) → Claude Opus 5 (xhigh) → Claude Opus 5 (max).

Key structural change from early July: GPT-5.6 replaced GPT-5.5; Claude Opus 5 replaced Opus 4.8;
Claude Fable 5 fell off (strictly dominated by Opus 5 max). See `references/pareto-snapshot-2026-07-26.md` for the full live extraction.

### 5. Evaluate a cheaper agentic executor as a routed replacement

When comparing a budget model to a premium executor, do not answer from price alone:

1. Resolve the exact live provider model ID. Reasoning levels such as `max` may be parameters rather than separate IDs.
2. Confirm tool calling, `tool_choice`, structured outputs, context window, and reasoning controls in the provider catalog.
3. Compare live cost per task and GDPval-AA first, then TerminalBench, coding, and TAU2. High TAU2 alone does not prove long-horizon recovery.
4. Replay the same real pipeline trace or task battery with identical plan, context, tools, turn budget, failure injection, and artifact verification.
5. Compute **cost per successful task**, not merely cost per token. A cheap failed run plus a premium retry may erase the apparent saving.
6. Prefer routing: budget model by default after validation, premium escalation for invalid reports, repeated tool failures, failed artifacts, or failed recovery.
7. State clearly whether the recommendation is benchmark-only or proven by a live A/B; never present a candidate replacement as already configured.

Dated example: `references/deepseek-v4-pro-vs-sonnet-5-july-2026.md` captures the live model ID, prices, benchmark gap, and routing interpretation from one executor comparison.

## Video Model Pricing

For media-generation models (video, image), see `references/video-model-pricing-july-2026.md` for the full cross-provider video generation matrix: Gemini Omni Flash, Seedance 2.0 (Fast/Standard/Mini), and Grok Imagine 1.5 across Google API, Kie.ai, Fal.ai, and xAI direct — including per-second rates, per-duration breakdowns, and the Kie.ai credit system. Also covers the Gemini Omni video API job-based async pattern (createTask → recordInfo polling) and the `video_list` extension mechanism.

For a concrete live comparison of MiniMax H3 across OpenRouter, Kie.ai, and fal.ai — including sticker versus effective rates, OpenRouter's credit fee, text-to-video versus reference-to-video input charges, and the verification workflow — read `references/h3-cross-platform-pricing-july-2026.md`. Use it as a dated reference, not as a permanent price snapshot.

For the 2026-08-06 four-model snapshot (Wan 3.0, Seedance 2.5, FLUX 3, MiniMax H3) — official FLUX 3 tiers, Seedance 2.5 opening token rates, and the class pitfalls (fal.ai blocks curl with a Vercel checkpoint, OpenRouter `/api/v1/models` excludes video models, per-token official pricing must not be converted to $/s by guesswork) — read `references/video-model-pricing-aug-2026.md`.

### Provider-price basis guardrail

Never turn “Kie is cheaper” into a universal provider rule. Normalize the exact model variant, endpoint, modality, resolution, duration, audio behavior, reference inputs, and billing unit before comparing. Separate three prices: the official model-provider/API list price, an intermediary’s representative or pass-through price (for example Artificial Analysis’s “representative API price”), and each marketplace’s retail SKU/credit price. A marketplace may undercut Fal.ai yet exceed the official API for another model; H3 versus Seedance exposed this distinction. If the official provider price is not verified, label the comparison provisional and do not use a marketplace discount claim as evidence.

## Live Pareto Snapshot

See `references/pareto-snapshot-2026-07-26.md` for the latest live extraction with the full frontier.
Always prefer a fresh extraction over any snapshot — model rankings and prices change weekly.

## Provider Price Comparison

See `references/provider-price-comparison-july-2026.md` for the full cross-provider price table
(OpenAI API, OpenRouter, Kie.ai) and Codex Plus subscription economics.

**Direct API benchmark methodology:** When comparing provider pricing for the same model, call both endpoints with identical prompts and compare real token usage + cost (not just theoretical $/M rates). Kie.ai GPT transport differs from Codex/API: input is a string (not message array), browser User-Agent (Chrome 131) is mandatory, and SSE is always-on. See `references/kie-gpt-benchmark-july-2026.md` for the live comparison script, text-only results (Kie.ai 69% cheaper, 3.9× slower), AND the tool-use benchmark (3-tool agentic loop: Kie.ai −84% cheaper, only 1.8× slower — tool-use amplifies savings because growing context is billed at Kie.ai's cheaper rates).

**Codex ChatGPT limitation:** GPT-5.6 Luna, Sol, and Terra are NOT available on Codex/ChatGPT accounts. The Responses API returns "not supported when using Codex with a ChatGPT account." Only GPT-5.5 and below work. For GPT-5.6 comparisons, use OpenRouter (same $1/$6 pricing as API) as the reference endpoint.

Historically stable structural truths (persist across releases):

- **DeepSeek V4 Pro** occupies the extreme-efficiency anchor (intel ~44, cost near-zero). It is the correct default for any task where 44 intel is sufficient.
- **Grok 4.5 (high)** is the best non-OpenAI, non-Claude premium model — typically 2–6× cheaper than Claude for comparable intelligence.
- **Claude Opus (top tier)** holds the absolute intelligence crown but at extreme cost — only justifiable when the task cannot tolerate a single error.
- **Claude Fable 5 is not on the frontier.** The top Opus tier strictly dominates it (higher intel + lower cost per task). Only consider Fable 5 if agentic benchmarks (GDPval-AA) materially separate it from Opus — check live data.
- **Chinese models (DeepSeek, MiniMax, GLM, MiMo) dominate the $0–$0.30 cost band.** Don't skip them when recommending value models.

### Kie.ai price-basis conflicts

Treat these as separate quantities:

- exact Kie input/output rates versus Kie’s explicit official-price basis;
- any discount claim written in the Kie page copy;
- Kie’s blended rate versus AA’s reference price.

If exact rates and an official basis exist, calculate the first comparison and retain the page claim separately. A difference above 2 percentage points is a `conflict`, not a reason to average the values. If no official basis exists, report `claim_only`; never label a page claim as an exact calculation. See `references/kie-pricing-conflicts.md` for the parsing and reporting contract.

## Subscription-Adjusted Analysis (GPT Plus / Copilot / etc.)

When the user accesses models through a **flat-fee subscription** (GPT Plus → Codex, Copilot, etc.),
the effective cost structure changes fundamentally. Do NOT treat subscription models as "free"
— they have a quota.

### Three-view subscription cost model

A flat-fee route must never be inserted into a single cost column as “free”.
Keep three views separate:

1. **Marginal / already-owned:** included Codex usage has marginal cash cost 0
   until the relevant quota is exhausted; this is the right view for routing when
   Monsieur already pays for Plus for other reasons.
2. **Full economic cost:** allocate the relevant share `alpha` of the monthly fee
   `F` to Codex and divide it by expected included usage. If `Q` is a token/credit
   quota and a task consumes `t_bar`, the approximate capacity is `N = Q / t_bar`
   and `cost_per_task = alpha * F / min(expected_tasks, N)`. Keep `alpha` explicit;
   do not silently charge the whole subscription to Codex when it also covers ChatGPT.
3. **Quota-saturated:** model the provider's exact top-up price, throttling, or
   fallback route after exhaustion. Never assume that exhaustion automatically
   means official API pricing.

The quota unit is part of the data contract. It may be raw tokens, weighted
credits, messages/tasks per rolling window, or a weekly cap. Record the unit,
window, input/output/cache/reasoning weights, model/tier identity, and whether the
limit is hard or estimated. If the UI exposes only messages or tasks, estimate
tokens per run from observed Codex usage and label the resulting capacity as an
estimate; never invent a token conversion. If the plan exposes credits with an
exchange rate `v` USD/credit, compute `B = F / v` credits for a fully allocated
fee, then for a task with token vector `(input, cache_read, cache_write, output,
reasoning)` use `credits_task = sum(tokens_k / 1e6 * credits_per_million_k)` and
`capacity = B / credits_task`. Report separate input/output equivalents
(`B / credits_per_million_k × 1e6`) and a mixed-task equivalent based on the
observed token profile; a single raw-token number is otherwise meaningless.

For every subscription route, store at least:
`billing_mode`, `monthly_fee`, `fee_allocation_alpha`, `quota_amount`, `quota_unit`,
`quota_window`, `overage_or_fallback_cost`, `model_identity_confidence`,
`quota_consumption_per_task`, and `effective_cost_per_task` for each scenario.
Run the Pareto calculation independently for **within-quota**, **full-economic**,
and **quota-saturated** scenarios. Add a capacity constraint (`expected_tasks <=
quota_capacity`) so a model that is cheap only for the first few tasks cannot
silently dominate a route with sufficient monthly capacity.

The AA task-cost field remains the benchmark's API task cost. It must not be
replaced by a subscription's token allowance unless the same task token profile
has been measured or a documented conversion is available. Report the quota
consumption and the cash cost side by side.

### Two-regime cost model

| Regime | Effective cost | When it applies |
|--------|---------------|-----------------|
| Within quota | Marginal cash cost = 0, with quota consumption recorded | Normal usage below the applicable limit |
| Quota exhausted | Exact top-up price, throttling, or explicit fallback route | Heavy usage, batch jobs, or agent loops |

### How to present subscription-adjusted analysis

1. **Ask the user for their effective quota** if they know it (messages/hour, tokens/month). If unknown, note the uncertainty.
2. **Produce two Pareto tables**: one assuming within-quota (OpenAI models at $0), one assuming API pricing (all models at market rate).
3. **The truth is usually in between.** Flag that the user's actual cost depends on their usage pattern. For light/intermittent use, the within-quota view dominates. For heavy agentic workloads, the quota will be exhausted and API pricing applies.
4. **Identify the "crossover"**: at what usage volume does the subscription model stop being cheaper than an API alternative? If GPT-5.6 Sol (max) costs $0.45/task at API rates and DeepSeek V4 Pro costs $0.045/task, the subscription pays for itself if the user would otherwise spend more on API calls than the subscription price — but only up to the quota.
5. **Never say "unlimited" or "free"** for subscription models. Always qualify with the quota constraint.

### Example framing

> Avec GPT Plus, GPT-5.6 Sol (max) a un coût marginal de $0 **dans la limite du quota**. Au-delà, il retombe à son prix API (~$0.45–$1.04/task selon le tier). La rentabilité réelle dépend de votre volume d'usage.

## Pitfalls

1. **cost_per_task ≠ blended $/1M.** The API's blended price is misleading. Always scrape the scatter chart for real task costs. Claude models are doubly penalized (higher $/1M AND higher tokens/task).
2. **Grok 4.5 omission is a critical error.** In any comparative analysis of top models, Grok 4.5 must be included. It dominates the premium-value quadrant. Failing to highlight it is a mistake the user will catch.
3. **The API key prefix matters.** Use `artificialanalysis/api_key` (prefix `aa_mgBk...`), not `artificial-analysis/api_key` (prefix `aa_LAdq...`). The latter returns 401.
4. **GDPval-AA (real agentic benchmark) is NOT in the API.** Use TAU2+TerminalBench+coding_index as proxy, but note this is approximate. The real GDPval-AA Elo rankings require scraping `/evaluations/gdpval-aa`.
5. **Chinese models dominate value.** DeepSeek, Xiaomi (MiMo), MiniMax, Z AI (GLM), and Alibaba (Qwen) occupy 80% of the attractive quadrant. Don't only recommend US models.
6. **Subscription ≠ unlimited.** GPT Plus, Copilot, and similar flat-fee plans have quotas. Never present subscription-accessed models as "free" or "unlimited." Always qualify with the two-regime model (within-quota = $0 marginal, exhausted = API pricing). Ask the user about their effective quota when they mention a subscription. Failing to do this produces misleading Pareto frontiers where subscription models appear to strictly dominate everything.
7. **GPT-5.6 NOT on Codex ChatGPT.** The Codex Responses API blocks GPT-5.6 Luna, Sol, and Terra on ChatGPT accounts ("not supported when using Codex with a ChatGPT account"). Only GPT-5.5 and below work. When the user asks for Codex vs Kie.ai comparison on GPT-5.6, use OpenRouter as the API-price reference (same $/M as official API). Do NOT spend time trying to make GPT-5.6 work on Codex — the restriction is server-side and repetitive probing triggers rate-limiting that makes ALL models return "not supported."
