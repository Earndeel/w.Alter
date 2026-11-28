# Design Arena API — reverse-engineered contract (verified Aug 2026)

Design Arena (designarena.ai) ranks models by **human preference Elo** on real
single-file HTML outputs (website, UI component, game, data-viz, 3D, SVG, ...).
No auth required; a standard Chrome user-agent works.

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/leaderboard` | POST | Elo leaderboards per arena+category |
| `/api/registry` | GET | Full model catalog (display names, providers, arenas) |
| `/api/leaderboard/judge-scores` | GET | Automated judge scores (fullstack build quality: schema design, CRUD ops, auth, UI interactivity, error handling, e2e persistence, ...) |
| `/api/leaderboard/llm-scores` | POST | LLM-judged composite build score per model + criteria breakdown |
| `/api/leaderboard/audiorealism` | GET | TTS/audio arena (separate set of models) |

### Leaderboard request

```json
{"arenaType": "models", "category": "allcategories", "variationName": "public"}
```

Response rows: `modelId, wins, losses, battles, winRate, elo, btStdErr, avgGenerationTimeMs`.
Metadata (overall only): `lastUpdateTime`, `totalVotes`.

### Valid categories (Aug 2026)

- **models**: `allcategories` (overall composite), `website`, `uicomponent`,
  `gamedev`, `dataviz`, `3d`, `svg`, `graphicdesign`, `logo`.
- **agents**: `fullstack`, `agon_webapps`, `mobileapps`, `nativeapps`,
  `agentic_3d`, `agon_dataviz`, `agon_html` — some return `data: []` legitimately
  (skip quietly). ⚠️ `webapps` is INVALID; it is `agon_webapps`.
- **builders**: `website`, `mobile`, `native-android`.
- `allcategories` for agents/builders returns `data: []` (no composite yet).
- "Image to Website" / "Video to Website" tabs are `website` +
  `inputModality: "image"|"video"`, NOT separate categories (`imagetohtml` invalid).

The canonical category → display mapping lives in the frontend chunk
`/_next/static/chunks/8603405ea5e7a40e.js` (constants `ARENAS`, `CATEGORY_REGISTRY`,
`CATEGORY_IDENTIFIER_TO_DISPLAY`).

## Rate limiting — the 400 trap

Rapid bursts of requests return **HTTP 400** (NOT 429) with
`{"success": false}` — the app frontend checks body `code: "rate_limit_exceeded"`.
Symptom: individual curl calls pass; a script looping categories fails on the
first or second call.

Mitigation (implemented in `collect_designarena.py`):
- `sleep(0.5)` between category requests;
- retry with exponential backoff (`1 + 2**attempt`, 4 attempts);
- treat 400 as retryable in general but log-and-skip genuinely invalid
  categories — distinguish by the `"Invalid category ..."` message in the body.

## Slug join rules (AA ↔ Design Arena)

- DA `modelId` uses dots/underscores (`gpt-5.6-sol`); AA slugs use hyphens and
  carry reasoning-tier suffixes (`gpt-5-6-sol-high`).
- Join = normalize (lowercase, dots/underscores → hyphen) then strip tier
  suffixes (`-low -medium -high -xhigh -max -non-reasoning -thinking -preview`)
  to map tiered AA rows onto the base DA model.
- Result: ~136 of ~582 AA rows match a DA base model. Unmatched tail = DA-only
  models (codec/date variants, e.g. `deepseek-v4-flash-0731`) or models DA does
  not publish.

## No price data

Neither the leaderboard nor the registry exposes token prices (the site's
"Preference vs Price" chart pulls them from elsewhere). To get Elo-vs-cost,
join DA Elo to the AA cost-per-task fields already in `latest.json` — that is
what `build_model_profiles.py` does.

## Pipeline (3 stages, daily cron 03:00)

```
refresh.py               → AA Intel/Agentic + Kie prices   → latest.json
collect_designarena.py   → DA Elo, 13 categories           → designarena.json
build_model_profiles.py  → AA × DA per-model join          → model_profiles.json/.csv
```

`~/.hermes/scripts/aa_pareto_daily_refresh.py` runs all three under
`/usr/bin/python3` (system Python, needed for Playwright in refresh.py) and
exits non-zero if any stage fails, so a broken cron surfaces.