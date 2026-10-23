# DesignArena + qualitative research ingestion notes

Use this when the model-router DB needs non-paid enrichment after paid execution tests are suspended.

## Trigger
If credits are exhausted or paid model calls are suspended, continue with free/metadata sources immediately instead of only preparing schema.

## Useful source discovered
DesignArena exposes leaderboard data at:

`https://www.designarena.ai/api/leaderboard/judge-scores`

The endpoint returns JSON with judge/model score rows. Useful fields observed:
- model identifier, e.g. `gemini-3.1-pro-preview`, `claude-fable-5`, `glm-5.2`, `glm-5.2-air`
- score/ELO-style values per judge
- enough structure to persist as external benchmark rows

Persist into `model_router.benchmarks` using source `designarena_api`, and store the raw row in `raw_payload`.

## Non-paid research pass checklist
1. Verify paid test cron/harness is paused before any provider execution calls.
2. Keep AA/OpenRouter catalog ingestion if it uses metadata/catalog endpoints only.
3. Run web searches per candidate model:
   - `"<model name>" LLM benchmark pricing context`
   - `"<model name>" OpenRouter`
   - `"<model name>" coding benchmark agent`
4. Run community searches with broader aliases when exact names are sparse:
   - model family + provider + `benchmark`, `coding`, `agent`, `OpenRouter`, `Artificial Analysis`
5. Store qualitative rows in `model_router.community_evidence` with:
   - `source`, `source_url`, `query`, `practical_feedback`, `evidence_quality`, `confidence`, `raw_payload`
6. Deduplicate by source URL/model where possible.
7. End with actual counts: models, endpoints, pricing snapshots, benchmarks, community evidence, ingestion runs.

## Pitfall
Do not treat four seed notes as "research done". A usable pass should leave each active candidate with multiple source-backed evidence rows, not decorative SQL confetti.
