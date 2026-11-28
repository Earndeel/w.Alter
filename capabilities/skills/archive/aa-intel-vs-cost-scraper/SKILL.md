---
name: aa-intel-vs-cost-scraper
description: Use for live AA Intelligence and benchmark cost-per-task data.
version: 2.1.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [artificial-analysis, intelligence-index, cost-per-task]
    related_skills: [aa-pareto-model-optimizer]
---

# Artificial Analysis live cost-per-task extraction

## Preferred path

For the complete dataset, use the unified deterministic collector from
`aa-pareto-model-optimizer`:

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/refresh.py --quiet
```

It collects the live AA Intelligence model-context RSC payload; optional Kie.ai pricing is added only when explicitly enabled. The separate `refresh_modalities.py` collector handles TTS, speech-to-speech, image, and video task leaderboards.

Read `$HERMES_HOME/cache/aa-pareto/latest.json` rather than pasting raw pages into
context. `latest.csv` is convenient for filtering; the raw JSON files are for
parser debugging only.

## Intelligence extraction

Use the full model-context RSC payload embedded in an AA model page. Extract every model object with `intelligenceIndex` and `intelligenceIndexCostPerTask.cost.total`. Parse the global `models` list and the page's `currentModel`; merge by exact slug, with `currentModel` authoritative, and reject the extraction if the requested anchor slug is still absent.

The Recharts Intelligence-vs-Cost plot is a page-dependent subset and is not the primary source. Its payload can be inspected for diagnostics only; never infer values from SVG coordinates or use the visible chart to establish catalog completeness.

The corresponding fields are:

- `intelligenceIndex` → `intelligence_index` (AA points)
- `intelligenceIndexCostPerTask.cost.total` → `aa_cost_per_task_intelligence_usd` (USD per Intelligence benchmark task)

Keep full precision until display rounding. Missing or non-positive cost is unavailable, not free.

Multimodal AA leaderboard data is collected separately by `refresh_modalities.py`. Keep each task's published score and price unit separate from Intelligence; do not construct cross-task cost frontiers without compatible benchmark-task costs.

## Metric discipline

Do not mix these metrics:

| Field | Unit | Use |
|---|---|---|
| `intelligence_index` | AA points | Intelligence benchmark quality |
| `aa_cost_per_task_intelligence_usd` | USD / Intelligence benchmark task | Intelligence benchmark efficiency |
| `price1mBlended0To3To1` | USD / 1M tokens | API price comparison |
| `costPerTask.total` | USD / benchmark task | benchmark efficiency |
| `evalCost.total` | USD / complete evaluation | full-run budget |

Missing or non-positive cost is unavailable, not free. Exclude it from a Pareto
frontier and retain an explicit status. Keep full precision until the final
display rounding.

## Kie.ai handoff

Kie pricing is not a universal percentage. The unified collector checks each
mapped Kie model page and stores:

- exact Kie input/output rates when exposed;
- Kie’s published official-price basis when exposed;
- nominal and explicitly supported top-up-adjusted reductions;
- the signed Kie-vs-AA reference-price delta.

Use `kie_pricing_status` as the gate. A row marked `unverified`, `not_found`, or
`fetch_error` must not receive a guessed discount from another model.

## Standalone script

The original Recharts extractor remains available for debugging:

```bash
python3 ~/.hermes/skills/research/aa-intel-vs-cost-scraper/scripts/extract_recharts.py gpt-5-5
```

Use its JSON output only as an extraction diagnostic; use the unified refresh
artifact for recommendations and Pareto decisions.

## Verification checklist

- [ ] Data was fetched live during this run.
- [ ] Intelligence rows came from the full RSC model context, including `currentModel` and the requested anchor.
- [ ] Multimodal task tables, if requested, remain separate with their quality and price units intact.
- [ ] Cost units are stated next to every reported number.
- [ ] Missing prices were excluded or marked, never converted to zero.
- [ ] Retrieval timestamp and source URLs are retained.
