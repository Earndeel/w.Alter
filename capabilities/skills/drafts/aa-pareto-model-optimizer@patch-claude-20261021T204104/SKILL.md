---
name: aa-pareto-model-optimizer
description: Use when Monsieur asks for an ad-hoc AA Pareto report (intelligence frontier, upgrade ladder, multimodal leaderboards) beyond what Walter Router already shows.
version: 5.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [artificial-analysis, llm, pareto, intelligence, tts, speech-to-speech, image, video]
    related_skills: [aa-intel-vs-cost-scraper, model-value-analysis, model-benchmark-comparison, walter-model-router]
---

# Artificial Analysis Pareto Optimizer

## Absorbed into Walter Router (2026-10-21)

Walter Router collects these sources itself, without a browser, every 48 h and on demand: AA Intelligence + cost per
task (`/walter/router/research/benchmarks/aa.py`), AA media leaderboards (`aa_media.py`), Design Arena
(`design_arena.py`); the Pareto mathematics (`make_frontier`, `ladder_knee`) lives in `/walter/router/analysis/pareto.py`.
For anything the router uses, read the router, not this cache:

- `walter-router library` (or https://library.walter-ai.cloud): per-task choice, tiers L1/L2/L3, prices, leaderboards;
- `walter-router dossier <task>`: every candidate with its per-board evidence;
- SQL on `models.benchmarks` / `models.offers` (see `/walter/router/docs/DATA.md`).

`~/.hermes/cache/aa-pareto/` is no longer refreshed by any timer (the cycle stopped calling
`aa_pareto_daily_refresh.py`; its Hermes cron 096741a21a32 stays paused). Use the scripts below only for an ad-hoc
report (strict / pragmatic frontier, upgrade ladder): they fetch live data themselves.

## Purpose

Build a current, reproducible comparison from live Artificial Analysis (AA) data:

- the AA Intelligence Index and its matching Cost per Task;
- separate AA leaderboard modules for provider-voice TTS, speech-to-speech, text-to-image, text-to-video, and image-to-video;
- an Intelligence Pareto frontier; multimodal leaderboards retain their published quality and price units and are not force-fit into a cost-per-task frontier;
- an `upgrade_ladder` anchored on the strongest global supported knee, then reduced to the upper concave envelope of score versus raw incremental task cost;
- a diagnostic `standout_frontier` containing local knees that must not be presented as globally useful upgrades.

The collector is deterministic and makes no LLM call. Do not derive the model table manually inside the context window. The optional subscription stage reads `$HERMES_HOME/cache/aa-pareto/subscriptions.json` and writes `subscription-adjusted.json` with credit/token equivalents and marginal/full/saturated cost views.

## Fast path

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/refresh.py --quiet
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/collect_designarena.py --quiet
```

`refresh.py` collects the AA Intelligence axis. `refresh_modalities.py` independently collects TTS, speech-to-speech, image-generation, and video-generation leaderboards; run it for multimodal data:

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/refresh_modalities.py --quiet
```

Read:

```text
$HERMES_HOME/cache/aa-pareto/latest.json         # AA Intelligence + optional Kie pricing
$HERMES_HOME/cache/aa-pareto/multimodal_latest.json # AA TTS, speech-to-speech, image, and video
$HERMES_HOME/cache/aa-pareto/latest.csv
$HERMES_HOME/cache/aa-pareto/designarena.json    # Design Arena human-preference Elo
$HERMES_HOME/cache/aa-pareto/model_profiles.json # per-model AA + DA competence join
$HERMES_HOME/cache/aa-pareto/model_profiles.csv
```

If `HERMES_HOME` is absent, the collectors resolve the active Hermes home when possible and otherwise use the default profile home.

## Design Arena stage (human preference > synthetic benchmarks)

`refresh.py` covers the AA Intelligence benchmark and optional Kie.ai pricing. Add the **Design Arena** stage to bring in human preference,
which ranks real judged HTML output (website, UI component, game, data-viz, 3D)
and can disagree with synthetic indexes:

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/collect_designarena.py --quiet
```

- Collects the `models` arena (public variation) across `allcategories`
  (overall), `website`, `uicomponent`, `gamedev`, `dataviz`, `3d`, `svg`,
  `graphicdesign`, `logo` — each row: model, Elo, win rate, battles, generation
  time. Also snapshots the full `/api/registry` (display names, providers,
  arenas).
- `modelId` uses dots (`gpt-5.6-sol`); AA slugs use hyphens (`gpt-5-6-sol`).
  Join on the normalized `slug_norm` field included in each Design Arena row
  and in `registry`. Roughly 78 frontier models match AA; unmatched tail
  models (mostly DA-only/codec variants) stay in `registry` for reference.
- The former cron wrapper `~/.hermes/scripts/aa_pareto_daily_refresh.py` (no longer scheduled) runs
  every stage sequentially (`refresh.py --with-kie` → `subscription.py` →
  `refresh_modalities.py` → `collect_designarena.py` → `build_model_profiles.py`
  → `router.py`) under the system Python, and exits non-zero if any stage fails.

Design Arena endpoints (reverse-engineered, no auth):
- `POST /api/leaderboard` with `{arenaType:"models"|"agents"|"builders", category, variationName:"public", inputModality?}` — Elo leaderboards. Valid models categories: `allcategories` (overall), `website`, `uicomponent`, `gamedev`, `dataviz`, `3d`, `svg`, `graphicdesign`, `logo`. Valid agents categories: `fullstack`, `agon_webapps`, `mobileapps`, `nativeapps`, `agentic_3d`, `agon_dataviz`, `agon_html` (some return 0 rows). `webapps` is invalid; "Image/Video to Website" = `website` + `inputModality`.
- `GET /api/registry` — full model catalog (display names, providers, arenas).
- A polite `sleep(0.5)` between categories plus backoff retries avoids the API's transient 400/429 rate limiting (individual curl calls pass; rapid bursts get 400).

## Per-model competence profiles (AA + Design Arena join)

`build_model_profiles.py` joins the AA Pareto snapshot with Design Arena into
per-model profiles: for every AA model that matches a DA model you get
the Intelligence Index + its matching AA cost per task, plus a Design Arena
competence block per category (Elo, win rate, battles, and the model's rank
within that category).

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/build_model_profiles.py --quiet
```

- AA slugs carry reasoning-tier suffixes (`gpt-5-6-luna-high`) while DA keys
  models at base level (`gpt-5.6-luna`); the join strips tier suffixes and
  normalizes dots/underscores to hyphens, so tiered AA rows inherit the base
  model's competence profile.
- Outputs `model_profiles.json` (full profiles) and `model_profiles.csv`
  (one row per AA slug; columns per category: Elo + rank). Read the CSV for
  reporting — it is the join table for "model X is good at Y".
- About 136 of 582 AA rows match DA (base models; the rest are tier/date
  variants or models DA does not publish).

## Live extraction contract

### Intelligence

Use the full model-context RSC payload embedded in an AA model page. Extract every model object having:

```text
intelligenceIndex
intelligenceIndexCostPerTask.cost.total
```

AA may omit the page's own model from the global `models` array while exposing it separately as `currentModel`. Parse both, merge them by exact slug (with `currentModel` authoritative), and reject the extraction if the requested anchor slug is still absent. This guard prevents a valid frontier model such as GPT-5.6 Luna max from silently receiving a null Intelligence score.

The RSC payload is present in the raw HTML of the model page (Walter Router reads it with a plain HTTP fetch since 2026-10-21); this skill's `refresh.py` still uses Playwright, which can transiently exceed 60 seconds. Run its navigation → settle → extraction → parsing sequence up to three times, with 1s/2s exponential backoff and a fresh browser context per attempt.

Do not scrape the visible Recharts comparison plot as the primary source. It contains a page-dependent subset and can silently omit valid frontier models.

### Multimodal AA leaderboards

Run `scripts/refresh_modalities.py` separately from the Intelligence collector. It stores task-separated AA data for:

| Module | Task | AA quality metric | Cost treatment |
|---|---|---|---|
| TTS | `provider_voice` | Provider Voice Elo | API price is reference-only; AA does not publish benchmark-task cost |
| Speech-to-speech | `index` | Speech to Speech Index | Preserve AA benchmark cost per input-audio hour and provider hourly rates as distinct units |
| Image | `text_to_image` | Text-to-Image Arena Elo | API price is reference-only; no benchmark-task cost |
| Video | `text_to_video`, `image_to_video` | Corresponding Arena Elo | API price is reference-only; no benchmark-task cost |

The output is `multimodal_latest.json` plus a flat `multimodal_latest.csv`. Compare quality only within the same task and keep each published price unit intact. Do not use API list prices as a substitute for benchmark cost, do not compare unrelated task scores, and do not construct cross-task Pareto frontiers without compatible benchmark-task costs. Missing values remain null.

### Merge

The Intelligence collector joins only Intelligence records by AA slug. Multimodal leaderboards are stored separately by module and task; do not merge them into the Intelligence model rows or inherit Intelligence task costs for image, video, TTS, or speech-to-speech models.

## Data contract — schema version 10

Each row in `latest.json.data` is one AA model configuration on the Intelligence axis. Multimodal records use the separate schema-versioned `multimodal_latest.json` snapshot.

| Field | Meaning |
|---|---|
| `name` | AA display name including tier when published |
| `slug` | Exact AA model slug |
| `intelligence_index` | AA Intelligence Index |
| `aa_cost_per_task_intelligence_usd` | Matching AA Intelligence Cost per Task |

Compare only Intelligence Index against its matching Intelligence Cost per Task. Multimodal metrics are separate and use their own published units.

## Pareto policy

Compute the Intelligence surface only:

```text
frontiers.intelligence_aa:
  maximize intelligence_index
  minimize aa_cost_per_task_intelligence_usd
```

### 1. `strict_frontier`

All mathematically non-dominated rows:

```text
A dominates B when:
A.score >= B.score
AND A.cost <= B.cost
AND at least one inequality is strict
```

This remains the reference frontier.

### 2. `supported_frontier`

Upper concave envelope of score versus natural-log cost. These are globally supported trade-offs under a proportional-cost utility. This view is useful mathematically but may be too aggressive for practical tier discovery.

### 3. `upgrade_ladder` — primary decision view

Pareto optimality alone cannot decide whether a score gain justifies a price increase without an explicit utility policy. Use a transparent marginal-return policy:

1. choose the strongest knee on the global `supported_frontier` as the `value_anchor`;
2. keep strict-frontier rows above that anchor in ascending raw AA task cost;
3. compute each incremental return as `delta score / delta task cost`;
4. build the upper concave envelope by removing every interior row where marginal return rises toward the next model instead of diminishing;
5. retain the maximum-score endpoint as `quality_ceiling`.

The retained sequence has monotonically decreasing marginal score gained per additional dollar. This is the set of discrete models that can be optimal for some linear willingness to pay for benchmark score. There is no fixed 5% performance band and no configurable score-spacing threshold in this decision layer.

Each tier reports:

```text
actual_uplift_pct_from_anchor
score_gain_from_anchor
cost_multiple_from_anchor
previous_tier
score_gain_from_previous_tier
cost_increase_from_previous_tier_usd
marginal_score_per_dollar_from_previous
incremental_cost_per_score_point
marginal_return_retained_vs_previous_segment_pct
```

Use `incremental_cost_per_score_point` as the break-even interpretation: advance to that tier only when one extra Index point is worth at least that many dollars per benchmark task. `removed_by_marginal_return` preserves every omitted row plus its previous/next models and incoming, outgoing, and bypass marginal returns.

A point such as GLM-5.2 or GPT-5.6 Sol xhigh may remain mathematically non-dominated yet be removed from the upgrade ladder when a later model offers a more efficient incremental upgrade. Never delete it from `strict_frontier`.

`quality_ceiling` remains visible because maximum quality can be rational when cost has near-zero weight, even if its final marginal return is poor.

### 4. `pragmatic_frontier` — value-filtered report view

Build this view for the Intelligence axis only; modality metrics are handled in their separate task datasets:

1. start from `epsilon_frontier`;
2. remove score steps below `minimum_gain` (default `0.5` Index points) compared with the last retained candidate;
3. walk candidates from cheapest to most expensive, comparing each with the last retained candidate;
4. remove a candidate when its incremental AA benchmark-task cost exceeds `max_incremental_cost_per_score_point` (default `$0.75` per additional Index point); after a removal, compare the next candidate against the last retained one.

This absolute marginal-cost cap is a practical value filter, not part of strict Pareto mathematics. A point can remain in `strict_frontier` and be removed from `pragmatic_frontier`; inspect `removed_by_cost_inefficiency` for the rejected model, comparison model, incremental cost, and threshold. The `quality_ceiling` stays separately visible in `upgrade_ladder` even when it exceeds the practical cap.

### 5. `standout_frontier` — local diagnostic only

Compare each interior strict-frontier point with its immediate cheaper and dearer neighbors. Keep endpoints and local knees whose incoming/outgoing marginal score-per-log-cost ratio reaches `--min-knee-strength` (default `2.0`).

Use this view to explain local geometry, never as the normal recommendation shortlist. Immediate-neighbor artifacts can make a globally redundant model look exceptional.

### Compatibility views

`epsilon_frontier` and `pragmatic_frontier` remain available in schema version 10. `strict_frontier` remains the mathematical audit view; use the `pragmatic_frontier` for the value-filtered report table and `upgrade_ladder` for normal recommendations.

## Thresholds

Defaults:

```text
Intelligence Index > 35
minimum knee strength = 2.0 (diagnostic only)
maximum marginal AA task cost = $0.75 per additional Index point
```

The upgrade ladder has no score-step threshold. Override the practical frontier's value cap, eligibility, or diagnostic knee when needed:

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/refresh.py \
  --min-intel 45 \
  --min-gain 0.5 \
  --min-knee-strength 2.5 \
  --max-incremental-cost-per-score-point 0.75
```

AA-only is the default. `--with-kie` is the optional live Kie.ai stage. When enabled, `refresh.py` reads the public pricing-table API (`https://api.kie.ai/client/v1/model-pricing/page`) and groups its per-direction records (Input, Cached Input, Cache Writes, Output) by model family before falling back to model-page HTML. A model page showing a placeholder such as `wocx` is not evidence that pricing is absent: verify the pricing-table API first. Kie translated costs remain estimates obtained from the Kie/AA blended token-price ratio and must be reported separately from the AA frontier.

## Recompute an existing snapshot

Use `pareto.py`; it writes the standout view to CSV:

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/pareto.py \
  "$HERMES_HOME/cache/aa-pareto/latest.json" \
  --intel-field intelligence_index \
  --cost-field aa_cost_per_task_intelligence_usd \
  --min-intel 35 \
  --min-knee-strength 2 \
  --max-incremental-cost-per-score-point 0.75 \
  --output /tmp/intelligence-pareto.json \
  --csv /tmp/intelligence-standouts.csv
```

For TTS, speech-to-speech, image, or video, inspect the matching task in `multimodal_latest.json`; those task leaderboards do not share a common benchmark-cost unit with Intelligence.

## Artifacts

```text
$HERMES_HOME/cache/aa-pareto/latest.json
$HERMES_HOME/cache/aa-pareto/latest.csv
$HERMES_HOME/cache/aa-pareto/raw-intelligence.json
$HERMES_HOME/cache/aa-pareto/history/YYYY-MM-DD.json
```

Raw snapshots exist for debugging, not normal reasoning.

## Scheduled refresh

No longer scheduled: Walter Router owns the periodic collection (2026-10-21). Run the scripts by hand when an ad-hoc report needs a fresh cache.

## Router engine (historical: superseded by Walter Router)

`router.py` was the first implementation of the three intelligence levels + conditional Design Arena escalation. Walter
Router now owns routing (tiers L1/L2/L3 by the owner's method in `/walter/router/docs/TIERS.md`, specialised tasks by
weighted leaderboards); do not route from `router_matrix.json`. The script stays for comparison only:

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/router.py            # full report
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/router.py --list-domains
```

## Interpretation order

Every AA intelligence Pareto report must contain these primary tables, in this order:

1. **Intelligence — pragmatic value frontier:** every row from `frontiers.intelligence_aa.pragmatic_frontier`, with model, Intelligence Index, matching AA Cost per Task, marginal cost per point, and useful cost/score deltas. Apply epsilon replacement, the minimum score gain (default `0.5`), then the maximum incremental cost per point (default `$0.75`) against the last retained model.
2. **Recommended — marginal selection:** the useful tiers from the Intelligence `upgrade_ladder`, with role (`value_anchor`, `marginal_upgrade`, or `quality_ceiling`), score, matching cost, incremental score gain, and `incremental_cost_per_score_point`.

When multimodal data is requested, report separate task-specific sections for TTS, speech-to-speech, text-to-image, text-to-video, and image-to-video; show AA's quality and cost units verbatim and do not combine them into Intelligence tables.

Do not use `strict_frontier` in either primary Pareto table: it is a mathematical audit view that preserves economically immaterial gains such as GLM-5.2 over Muse Spark. Show it only in an explicitly labeled appendix when Monsieur asks for the raw mathematical frontier.

Before the tables, report `generated_at` and source row counts. After them, explain notable exclusions through `removed_by_epsilon`, `removed_by_min_gain`, `removed_by_cost_inefficiency`, or `removed_by_marginal_return` only when they affect the recommendation or Monsieur asks why a model is absent. Interpret `incremental_cost_per_score_point` as the break-even willingness to pay for one extra Index point, not as an unconditional recommendation. Use `standout_frontier` only to diagnose local knees.

Never manufacture a shortlist from a partial chart or omit a model merely because it was absent from one comparison page.

When presenting router candidates from a catalog, distinguish catalog membership from Pareto eligibility: a low API token price alone does not qualify a model as a value recommendation. Verify recommendations against the current task-specific frontier using compatible quality/cost measurements; do not label a model fast without measured latency or throughput. Keep dominated models in the historical/catalog data, but exclude them from that frontier's recommendations. Explain whether a correction concerns stored evidence, computed selection, or the assistant's presentation before changing code or deleting records.

## Verification

Run:

```bash
cd ~/.hermes/skills/research/aa-pareto-model-optimizer
python3 -m pytest -q tests
python3 -m py_compile scripts/refresh.py scripts/pareto.py
python3 scripts/refresh.py --quiet --output-dir /tmp/aa-pareto-check
```

Then verify:

- the live AA Intelligence source returned a non-empty dataset;
- Intelligence rows came from the full RSC model context, not Recharts;
- the RSC global `models` array was merged with `currentModel`, and the requested anchor slug is present in the final Intelligence records;
- the Intelligence frontier uses only its matching benchmark cost field;
- when modalities are refreshed, all five task tables are present and their AA quality/price units remain separate;
- the pragmatic frontiers enforce the configured marginal-cost cap and report excluded rows in `removed_by_cost_inefficiency`;
- any model removed by the practical cost cap remains available in `strict_frontier`, and `quality_ceiling` remains separately reported;
- `upgrade_ladder` starts at the strongest global supported knee;
- every retained tier has a strictly lower `marginal_score_per_dollar_from_previous` than the prior segment;
- every omitted interior strict-frontier point appears in `removed_by_marginal_return` with its previous/next models and incoming/outgoing marginal returns;
- each standout's neighbor fields still refer to the strict frontier;
- `pareto.py` reproduces the same upgrade-ladder model names from `latest.json`;
- display rounding occurs only after comparisons.

## Common failures

- **AA RSC shape changed:** inspect the Intelligence raw snapshot and update the parser; never guess field names. Intelligence comes from the full model-context RSC.
- **Anchor page unavailable:** pass another valid `--anchor-slug`; the full model-context RSC is the target, not the page's visible chart.
- **Missing cost:** exclude the row from that axis only; missing is not free.
- **Unexpectedly tiny Intelligence universe:** reject the run and inspect RSC extraction rather than falling back silently to a comparison chart.
- **Modalities missing:** rerun `refresh_modalities.py`; it must match each AA task table's expected headers. Do not substitute API list prices for benchmark costs, or stale modality data for a failed refresh.
- **Stale result:** compare `generated_at` with the requested freshness window and rerun the collector.
