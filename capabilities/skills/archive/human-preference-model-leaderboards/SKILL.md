---
name: human-preference-model-leaderboards
description: Collect Design Arena Elo and join it with AA benchmarks.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [design-arena, leaderboard, elo, human-preference, model-selection, pareto]
    related_skills: [aa-pareto-model-optimizer, live-data-payload-drift, aa-intel-vs-cost-scraper]
---

# Human-Preference Model Leaderboards

## Purpose

Collect Elo ratings from **crowdsourced human-preference** model leaderboards —
benchmarks where real users judge actual outputs (the reference is Design
Arena, designarena.ai) — and join them with synthetic benchmark data
(Artificial Analysis Intelligence/Agentic Index) so model selection reflects
human taste, not only synthetic indexes.

Why it matters: human preference **disagrees with synthetic benchmarks**.
Verified example (Aug 2026): Kimi K3 is #1 overall in Design Arena (Elo 1414,
66.7% win) while AA Intelligence puts it 3.4 points *behind* Claude Opus 5;
DeepSeek V4 Flash is the AA cost anchor but ranks #50 in human preference
(48.9% win, 28k battles). Synthetic-optimal ≠ human-preferred.

## When to Use

- Monsieur asks for a Pareto/stack analysis enriched with human judgment
  ("which model is actually good at design/3D/frontend").
- A model-selection question where a deliverable is judged visually
  (website, UI component, 3D, data-viz, game, SVG, logo).
- Any "which models are best at X" that should weigh user votes, not just
  benchmark scores.

## Collector

```bash
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/collect_designarena.py --quiet
python3 ~/.hermes/skills/research/aa-pareto-model-optimizer/scripts/build_model_profiles.py --quiet
```

Artifacts (written to `$HERMES_HOME/cache/aa-pareto/`):

- `designarena.json` — raw leaderboards: 9 model-arena categories
  (`allcategories` = overall, `website`, `uicomponent`, `gamedev`, `dataviz`,
  `3d`, `svg`, `graphicdesign`, `logo`) + 4 agentic-build categories
  (`fullstack`, `agon_webapps`, `mobileapps`, `nativeapps`) + full
  `/api/registry` model catalog (display names, providers, arenas).
- `model_profiles.json` / `model_profiles.csv` — per-model join: AA
  intelligence/agentic indexes + AA cost per task + Design Arena competence
  block per category (Elo, win rate, battles, rank within category).

Run order matters: `refresh.py` (AA) first, then collect, then profiles.

## Report pattern

A typical deliverable is a competence table per model:

| Model | AA Intel | Overall rank | 3D | Website | UI Comp. | Best competence |
|---|---|---|---|---|---|---|

Plus the "human truth" takeaways: which AA-anchored model is weak at design,
which mid-tier model humans actually prefer, and the per-category specialists.

## Pitfalls

- **Rate limiting returns HTTP 400, not 429** — rapid bursts get
  `{"success":false}` with `code: rate_limit_exceeded` in the body. Individual
  curl calls pass; scripts that hammer categories fail on call 1-2. Mitigate
  with `sleep(0.5)` between categories + exponential backoff retries.
- **`webapps` is an INVALID agents category** — it is `agon_webapps`. Invalid
  categories return 400 with `"Invalid category ..."` in the body.
- **"Image to Website" / "Video to Website" are NOT separate categories** —
  they are `website` + `inputModality: "image"|"video"`. `imagetohtml` 400s.
- **Slug conventions differ**: DA uses dots (`gpt-5.6-sol`), AA uses hyphens
  plus reasoning-tier suffixes (`gpt-5-6-sol-high`). Join on normalized base
  slug: lowercase, dots/underscores → hyphens, strip tier suffixes
  (`-low -medium -high -xhigh -max -non-reasoning -thinking -preview`).
  ~136 of ~582 AA rows match DA base models; the rest are tier/date variants.
- **No price data in DA** — neither leaderboard nor registry exposes token
  prices. For Elo-vs-cost analysis, join DA Elo to AA cost-per-task fields.
- **agents/builders `allcategories` returns `data: []`** — no composite exists
  for those arenas; skip quietly.

## Pattern reuse

The DA API shape (POST `/api/leaderboard` + GET `/api/registry`) is the
reference reverse-engineering contract — see
`references/design-arena-api.md` for endpoints, valid categories per arena,
and the 400-rate-limit dissection. If Design Arena changes shape, treat it as
payload drift: see `live-data-payload-drift` for the generic fix pattern.

## Verification

- [ ] `designarena.json` has rows in every expected category
- [ ] `model_profiles.csv` exists with rank columns populated
- [ ] Overall column matches the live site top (Kimi K3 leader in Aug 2026)
- [ ] Cron wrapper `aa_pareto_daily_refresh.py` exits 0 under /usr/bin/python3