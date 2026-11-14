# Artificial Analysis MCP + X/Reddit dry-run notes — 2026-06

Session learning for the model-router intelligence loop.

## Artificial Analysis API/MCP

- `AA_API_KEY` was available in `/root/.hermes/.env` and the Artificial Analysis API responded at `https://artificialanalysis.ai/api/v2`.
- A local Hermes MCP wrapper was created at `/root/.hermes/mcp_servers/artificial_analysis_mcp.py` and configured as `mcp_servers.artificial-analysis`.
- Smoke-test result: API status OK, sample endpoint returned keys including `status`, `prompt_options`, `data`.
- Useful fields observed for router scoring include Intelligence, Coding, GPQA, HLE, TAU2/tool-use-style scores, pricing input/output/blended, speed/context where available.
- Example live observation from GLM-5.2 max during the session: Intelligence ~51.1, Coding ~68.8, GPQA ~0.895, HLE ~0.401, TAU2 ~0.991, with input/output/blended prices exposed by AA. Treat values as time-sensitive and re-fetch rather than hardcoding.

## Workflow correction from Monsieur

Do not jump straight to recurring cronjobs. For this class of system, first deliver:

1. project summary,
2. explicit loop architecture,
3. data contracts between loops,
4. dry-run plan,
5. dry-run execution and sample output,
6. only then cron/integration.

Cron creation before architecture made the system unclear and fragile.

## XSearch notes

- `x_search` worked for simple model/provider queries.
- Overly complex boolean soup queries failed or returned poor signal.
- Use decomposed searches: one model/provider/claim per query, then merge/deduplicate downstream.
- Recommended query groups:
  - `<model> benchmark`
  - `<model> pricing`
  - `<model> OpenRouter`
  - `<model> Artificial Analysis`
  - `<provider> free credits OR trial OR free tier`
  - `<model> tool calling OR coding OR long context`

## Reddit notes

- Reddit RSS/search endpoints are useful as a low-friction public fallback.
- Exact searches for very new model names can return no results even when adjacent discussion exists.
- Use subreddit whitelist plus broad queries first, then filter:
  - r/LocalLLaMA
  - r/ClaudeAI
  - r/OpenAI
  - r/OpenRouter when available
  - r/MachineLearning
  - provider-specific subreddits if active
- Start broad: `new model`, `pricing`, `benchmark`, `OpenRouter`, `free credits`, provider name, then match candidate models in titles/bodies.

## Router Loop 1 source priority

Recommended source stack:

1. AA MCP/API for structured benchmark/pricing ratios.
2. OpenRouter catalog/API/docs for availability and current route price.
3. Provider official docs/changelogs for direct pricing, cache, context, limits.
4. Design Arena for frontend/design signal.
5. XSearch for launch/offer/community trend discovery.
6. Reddit search/RSS for practical complaints and hands-on reports.
7. Browser/scraping fallback when API/RSS lacks the needed field.

## Anti-hype rule

A community signal should not promote a model by itself. It may trigger tests, increase confidence if corroborated, or flag risks. Promote only after benchmark/API data or W.Alter test harness evidence supports it.
