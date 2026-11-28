# aa-pareto-model-optimizer — The Design Arena stage and per-model competence profiles (AA + Design Arena join).

Moved verbatim from SKILL.md on 2026-11-01.

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
- The former wrapper (manual run only) chains refresh → collect → profiles.

