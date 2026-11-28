# Intelligence chart targeted-page fallback

## When to use

Use this whenever a model/tier requested for an Intelligence-vs-cost analysis is absent from the global Recharts payload. A global chart is a current subset, not a complete model catalog; absence from it is not evidence that AA lacks the metric.

## Reproduction

1. Open the exact AA model page, preserving the tier slug (for example, `claude-opus-5-medium`, not the base `claude-opus-5`).
2. Explicitly activate the `Intelligence vs. Cost per Task` view.
3. Extract the Recharts React payload attached to the scatter circles, not SVG coordinates or visual labels.
4. Read `payload.label`, `payload.x`, `payload.y`, `payload.url`, and `payload.reasoning`.
5. Verify that the returned URL, displayed label, and reasoning tier identify the requested model. Do not join `medium`, `high`, `xhigh`, and `max` through a shared base URL.
6. Only mark the model unavailable after the model-specific page itself has no valid Intelligence score and positive task cost.

The reusable probe is:

```bash
python3 /root/.hermes/skills/aa-pareto-model-optimizer/scripts/extract_recharts.py <exact-aa-model-slug>
```

The `x` field is USD per Intelligence benchmark task; `y` is the Intelligence Index.

## Verified regression case (2026-07-31)

The unified snapshot incorrectly marked `claude-opus-5-medium` as `missing_from_chart` because the global chart omitted it. The model page and targeted Recharts extraction returned:

| Model | Intelligence Index | AA cost/task |
|---|---:|---:|
| Claude Opus 5 (medium) | 56.2806227158121 | $0.7224261397230394 |
| Kimi K3 (max) | 57.1123394372091 | $0.8552042372493249 |

Kimi therefore gains only **1.4778029831%** Intelligence for an **18.3794702635%** cost premium and has **14.2775324495%** lower Index/$ value. Under a 5% `standout_frontier` score-jump rule, Kimi is not justified as the next material tier over Opus medium; both remain distinct candidates on the strict non-dominated frontier.

Source pages:

- https://artificialanalysis.ai/models/claude-opus-5-medium
- https://artificialanalysis.ai/models/kimi-k3

This example is diagnostic evidence for the extraction/join rule, not a permanent ranking. Always rerun the live probe before making a current recommendation.
