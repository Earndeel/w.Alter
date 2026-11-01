# Design Arena API contract (reverse-engineered, validated Aug 2026)

Base: `https://www.designarena.ai` — Next.js app, **no auth** for public
leaderboards. These endpoints feed `collect_designarena.py` /
`build_model_profiles.py` in `aa-pareto-model-optimizer` and the router
decision surface. Re-verify against live responses before relying on them
after a site change.

## POST /api/leaderboard — Elo leaderboards

Body: `{"arenaType": "models"|"agents"|"builders", "category": "<cat>", "variationName": "public", "inputModality": "<text|image|video>" (optional)}`

Response: `{"success": true, "arenaType": ..., "category": ..., "data": [rows], "metadata": {"lastUpdateTime", "totalVotes"}, "timestamp": ...}`

Row fields: `modelId, wins, losses, battles, winRate, elo, btStdErr, avgGenerationTimeMs`.

- `variationName: "public"` is REQUIRED — empty variation returns `data: []`.
- `metadata` (total votes, last update) is present on the `allcategories` response.
- Invalid category → `400 {"success": false, "message": "Invalid category ..."}` — permanent, do not retry.

### Valid categories per arena

| Arena | Valid categories |
|---|---|
| models | `allcategories` (overall), `website`, `uicomponent`, `gamedev`, `dataviz`, `3d`, `svg`, `graphicdesign`, `logo` |
| agents | `fullstack`, `agon_webapps`, `mobileapps`, `nativeapps`, `agentic_3d` (0 rows), `agon_dataviz` (0 rows), `agon_html` (0 rows) |
| builders | `website` (18 rows), `mobile`, `native-android` |

Traps discovered the hard way:
- "Image to Website" / "Video to Website" are NOT categories: `website` + `inputModality:"image"` / `"video"`.
- `imagetohtml`, `ui`, `ui-component`, `code` → invalid for models.
- `webapps` → INVALID for agents; the real key is `agon_webapps`.
- `agents/allcategories` → HTTP 200 but `data: []`.

## GET /api/registry — model catalog

`{"models": {"<id>": {id, displayName, provider, active, openSource, router, arenas: {models: [], agents: [], builders: []}, inputModalities: []}}}` — ~460 models; display names, providers, arena membership. No pricing fields.

## Other endpoints (discovery only)

- `POST /api/leaderboard/llm-scores` — judge-criteria composite:
  `[{modelId, llmScore, sampleCount, criteria: {schemaDesign, dataSeeding, apiFunctionality, crudOperations, authImplementation, uiInteractivity, e2ePersistence, errorHandling}}]` (7-pt scales).
- `GET /api/leaderboard/audiorealism?subcategory=...` — audio Elo.
- `GET /api/leaderboard/judge-scores` — `judge_fullstack` etc. composites.

## Rate limiting — the 400 trap

- Rapid bursts return **HTTP 400 (transient)**, NOT 429 (curl passes alone; immediate sequential calls get 400).
- Every 400 needs inspection: body `"Invalid category"` = permanent (stop); no-body 400 = transient (backoff + retry).
- Mitigation that works: `sleep(0.5)` between categories + retries with `1 + 2**attempt` backoff (4 attempts).

## Slug mapping between Design Arena and AA

- DA `modelId` uses dots (`gpt-5.6-sol`); AA uses hyphens (`gpt-5-6-sol`). Normalize: lowercase, `.`→`-`, `_`→`-`.
- AA slugs carry reasoning-tier suffixes (`gpt-5-6-luna-high`); DA keys base model (`gpt-5.6-luna`). Strip `-low/-medium/-high/-xhigh/-max/-non-reasoning/-thinking/-preview` repeatedly to join base.
- ~78 of 152 DA models match an AA slug (frontier models); the tail is DA-only variants (dated clones, thinking variants) or models AA does not publish.
- DA top-of-category leaders are per-category, NOT Overall: e.g. Data Viz leader is Claude Opus 5 (1389 in dataviz), while Kimi K3 leads the Overall scale (1415) but is #2 in Data Viz.
- Models without AA cost (e.g. gpt-image-2 in logo/graphic) are image/video generators outside the text-LLM pool — flag `in_llm_pool=false`.