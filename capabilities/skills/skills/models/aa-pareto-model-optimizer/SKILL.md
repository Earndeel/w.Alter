---
name: aa-pareto-model-optimizer
description: "Use when the owner asks for an ad-hoc AA Pareto report (intelligence frontier, upgrade ladder, multimodal leaderboards) beyond what Walter Router already shows. Also covers: aa intel vs cost scraper."
version: 5.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [artificial-analysis, llm, pareto, intelligence, tts, speech-to-speech, image, video]
    related_skills: [aa-intel-vs-cost-scraper, model-value-analysis, model-benchmark-comparison]
---

# Artificial Analysis Pareto Optimizer

## Absorbed into Walter Router (2026-10-21)

Walter Router collects these sources itself, without a browser, every 48 h and on demand: AA Intelligence + cost per
task (`research/benchmarks/aa.py`), AA media leaderboards (`aa_media.py`), Design Arena (`design_arena.py`); the
Pareto mathematics (`make_frontier`, `ladder_knee`) lives in `analysis/pareto.py`. For anything the router uses, read
the router, not this cache:

- `walter-router library` (or https://library.walter-ai.cloud): per-task choice, tiers L1/L2/L3, prices, leaderboards;
- `walter-router route "<request>"`: routing from a task description (replaces `router.py` for routing), and
  `walter-router pick <task> [--level L1|L2|L3]` for a known task;
- `walter-router dossier <task>`: every candidate with its per-board evidence;
- SQL on `models.benchmarks` / `models.offers` (see `/walter/router/docs/DATA.md`).

`~/.hermes/cache/aa-pareto/` is no longer refreshed by any timer (the cycle stopped calling
`aa_pareto_daily_refresh.py`; its Hermes cron 096741a21a32 stays paused). Use the scripts below only for an ad-hoc
report (strict / pragmatic frontier, upgrade ladder). Only the collectors fetch live data (`refresh.py`,
`refresh_modalities.py`, `collect_designarena.py`); `pareto.py`, `build_model_profiles.py` and `router.py` read the
cache: run the collectors first, then check `generated_at`, so a report is never built on stale data.

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

## Live extraction contract

### Intelligence

Use the full model-context RSC payload embedded in an AA model page. Extract every model object having:

```text
intelligenceIndex
intelligenceIndexCostPerTask.cost.total
```

AA may omit the page's own model from the global `models` array while exposing it separately as `currentModel`. Parse both, merge them by exact slug (with `currentModel` authoritative), and reject the extraction if the requested anchor slug is still absent. This guard prevents a valid frontier model such as GPT-5.6 Luna max from silently receiving a null Intelligence score.

Playwright navigation to either AA page can transiently exceed 60 seconds even when the site is healthy. Run the complete navigation → settle → inline-RSC extraction → parsing sequence up to three times, with 1s/2s exponential backoff and a fresh browser context per attempt. When running the full chain by hand, check it through the former wrapper `/root/.hermes/scripts/aa_pareto_daily_refresh.py` under `/usr/bin/python3` (manual run only; it is no longer scheduled).

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

## Interpretation order

Every AA intelligence Pareto report must contain these primary tables, in this order:

1. **Intelligence — pragmatic value frontier:** every row from `frontiers.intelligence_aa.pragmatic_frontier`, with model, Intelligence Index, matching AA Cost per Task, marginal cost per point, and useful cost/score deltas. Apply epsilon replacement, the minimum score gain (default `0.5`), then the maximum incremental cost per point (default `$0.75`) against the last retained model.
2. **Recommended — marginal selection:** the useful tiers from the Intelligence `upgrade_ladder`, with role (`value_anchor`, `marginal_upgrade`, or `quality_ceiling`), score, matching cost, incremental score gain, and `incremental_cost_per_score_point`.

When multimodal data is requested, report separate task-specific sections for TTS, speech-to-speech, text-to-image, text-to-video, and image-to-video; show AA's quality and cost units verbatim and do not combine them into Intelligence tables.

Do not use `strict_frontier` in either primary Pareto table: it is a mathematical audit view that preserves economically immaterial gains such as GLM-5.2 over Muse Spark. Show it only in an explicitly labeled appendix when the owner asks for the raw mathematical frontier.

Before the tables, report `generated_at` and source row counts. After them, explain notable exclusions through `removed_by_epsilon`, `removed_by_min_gain`, `removed_by_cost_inefficiency`, or `removed_by_marginal_return` only when they affect the recommendation or the owner asks why a model is absent. Interpret `incremental_cost_per_score_point` as the break-even willingness to pay for one extra Index point, not as an unconditional recommendation. Use `standout_frontier` only to diagnose local knees.

Never manufacture a shortlist from a partial chart or omit a model merely because it was absent from one comparison page.

When presenting router candidates from a catalog, distinguish catalog membership from Pareto eligibility: a low API token price alone does not qualify a model as a value recommendation. Verify recommendations against the current task-specific frontier using compatible quality/cost measurements; do not label a model fast without measured latency or throughput. Keep dominated models in the historical/catalog data, but exclude them from that frontier's recommendations. Explain whether a correction concerns stored evidence, computed selection, or the assistant's presentation before changing code or deleting records.

## Publishing selection for routers

- Publish versioned, hashed, task/objective-specific shortlists atomically, and have the router validate the artifact and source fingerprint before and after classification. Fail explicitly on a missing, stale, corrupt or unknown artifact instead of silently sorting the raw catalog.
- Preserve the current value anchor and quality ceiling before bounding a menu; taking the cheapest N frontier rows can omit the very anchor the policy selected. Explain further pruning and do not claim a bounded menu is globally optimal for every later quality floor.
- Distinguish measured dominance from missing comparable cost. A configuration with no matching benchmark cost is cost-ineligible, not proven dominated; quality-only and separately measured latency eligibility remain independent.
- Keep verified execution offers separate from benchmark menus. Neither subscriptions archived as provisional nor public provider prices establish exact mapping, entitlement, quota or free access.

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
- **Stale result:** compare `generated_at` with the requested freshness window and rerun the collector;

## Further reading (moved out of this file on 2026-11-01, unchanged)

- `references/historical-router-engine.md` — The former router engine, superseded by Walter Router (history).
- `references/pareto-policy.md` — Pareto policy and thresholds.
- `references/design-arena-and-profiles.md` — The Design Arena stage and per-model competence profiles (AA + Design Arena join).

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **aa-intel-vs-cost-scraper** — Extracting live Artificial Analysis intelligence and cost-per-task figures from the page (Recharts extractor script) and the metric discipline for cost per task.
  Read `references/merged-aa-intel-vs-cost-scraper/aa-intel-vs-cost-scraper.md` (+ 1 supporting file in that folder).
