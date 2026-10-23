# Design Arena API — reverse-engineered contract (verified Aug 2026)

Design Arena (designarena.ai) is a crowdsourced benchmark: real users vote on
single-file HTML outputs (website, UI component, game, data-viz, 3D, ...).
No auth is required; a desktop Chrome User-Agent works. Unlike the AA site,
the leaderboard data is served by plain REST endpoints — no Cloudflare/RSC
gymnastics needed for these paths.

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `GET /api/registry` | GET | Full model catalog (~460 models): `id`, `displayName`, `provider`, `active`, `openSource`, `router`, `arenas.{models,agents,builders}` (category lists), `inputModalities`. **No pricing fields.** |
| `POST /api/leaderboard` | POST json `{arenaType, category, variationName:"public", inputModality?}` | Elo leaderboard rows: `{modelId, wins, losses, battles, winRate, elo, btStdErr, avgGenerationTimeMs}` plus `metadata: {lastUpdateTime, totalVotes}`. |
| `POST /api/leaderboard/llm-scores` | POST `{}` | LLM judge scores per model (fullstack automation): `llmScore`, criteria `{schemaDesign, dataSeeding, apiFunctionality, crudOperations, authImplementation, uiInteractivity, e2ePersistence, errorHandling}`, `sampleCount`. |
| `GET /api/leaderboard/judge-scores` | GET | Per-category judge-score criteria (`judge_fullstack`, ...): `avg_composite` + criterion averages. |
| `GET /api/leaderboard/audiorealism` | GET `?subcategory=` | Audio / TTS realism arena (Elo, includes `human` at 1501). |

## Arena types and valid categories (verified)

- `models`: `allcategories` (overall composite), `website`, `uicomponent`,
  `gamedev`, `dataviz`, `3d`, `svg`, `graphicdesign`, `logo`. (registry also
  lists `ascii`, `image`, `video`, `slides`, `music`, ... — some return
  empty/400 on the leaderboard endpoint.)
- `agents` (agentic build): `fullstack` (34), `agon_webapps` (36),
  `mobileapps` (34), `nativeapps` (32), plus `agentic_3d`, `agon_dataviz`,
  `agon_html` (valid but 0 published rows). **`webapps` is NOT valid** -> 400.
- `builders`: `website` (18), `mobile`, `native-android`.
- "Image to Website" / "Video to Website" are **not** separate categories:
  they are `website` + `inputModality: "image"|"video"`.

## Response shape (leaderboard)

```json
{"success": true, "arenaType": "models", "category": "allcategories",
 "data": [{"modelId": "kimi-k3", "wins": 3078, "losses": 1537,
   "battles": 4615, "winRate": 66.7, "elo": 1414, "btStdErr": 5.55,
   "avgGenerationTimeMs": 628355}],
 "metadata": {"lastUpdateTime": "2026-08-08T10:28:36Z", "totalVotes": 1276032}}
```

## Rate-limiting pitfall (the one that wasted a session)

Rapid bursts return **transient HTTP 400** (not 429). A single curl or one
script call always passes; firing category after category gets 400s whose
body can even say `Invalid category` for a category that is actually valid.
Mitigation implemented in the aa-pareto collector (`collect_designarena.py`):
- `time.sleep(0.5)` between categories;
- `sleep(1 + 2**attempt)` backoff inside `request_json` (attempts=4);
- retry on 429 and 5xx; treat persistent-empty / repeated-400 as "skip
  category" for agent categories, never as a schema-change proof.
Do not conclude "invalid category" from a single 400 — re-probe with a pause.

## Slug joining rules (DA <-> AA)

- DA `modelId` / registry keys use dots: `gpt-5.6-sol`, `kimi-k3`.
- AA slugs use hyphens + tier suffixes: `gpt-5-6-sol-high`, `kimi-k3-low`.
- Join recipe: lowercase, dots/underscores -> hyphens, then strip tier
  suffixes (`-low`, `-medium`, `-high`, `-xhigh`, `-max`, `-non-reasoning`,
  `-thinking`, `-preview`). Tiered AA rows inherit the base model's DA
  profile (e.g. every `claude-opus-5-*` tier carries `claude-opus-5` DA rows).
- Result: ~136 of 582 AA rows match a DA base model; 152 models in overall.
- The registry is the authoritative name source: `display_name` for reports,
  `provider` for provider grouping.

## Design Arena judgment vs AA benchmarks (why this stage exists)

The Overall Elo correlates only loosely with AA Intelligence/Agentic Index.
Notable cases (Aug 2026): Kimi K3 = #1 human preference (1414 Elo, 66.7% win)
despite being ~3 pts behind Claude Opus 5 on AA Intel; DeepSeek V4 Flash is
the AA cost/task king but ranks ~#50 in human preference (48.9% win) — cheap
for text, risky for design deliverables. Always present both axes in routing
reports; do not substitute one for the other.

## RSC prefix lesson (same pipeline, artificialanalysis.ai side)

AA's inline Next.js flight payloads changed prefix from `c:` to `d:`
(Aug 2026); the aa-pareto `refresh.py` `strip_rsc_prefix()` now strips any
single-letter prefix (`^[a-zA-Z]:`) instead of a hardcoded `c:`. The Agentic
page now exposes a flat `models` array carrying `headlineValue` +
`costPerTask.total` plus new `price1m*` / `evalCost` fields —
`find_models_payload` matches on `headlineValue` presence, which still works.
When AA breaks again: dump the inline script, inspect the decoded pushes,
then patch — never guess field names. A 6-day silent cron failure was caused
by exactly this payload-shape change; always check cron last_status/error
before trusting cached artifacts' freshness.