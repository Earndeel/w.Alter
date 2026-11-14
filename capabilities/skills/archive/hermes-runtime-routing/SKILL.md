---
name: hermes-runtime-routing
description: Use when routing Hermes models, tools, and payloads.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, routing, models, providers, payload, cache, tools]
    related_skills: [hermes-agent, hermes-harness-auditing]
---

# Hermes Runtime Routing

Use this class-level skill for the shared runtime problem behind model selection, provider-family routing, delegated execution, deferred tool discovery, picker catalogs, prompt payload composition, cache behavior, and wire-level validation. Keep the user-facing catalog compact while preserving exact runtime transport and evidence.

## Always-on rules

- Separate presentation identity from runtime provider, endpoint, API mode, model ID, and auth scope; one picker row may route to several protocol families.
- Freeze the requested model/provider IDs exactly, then verify them against the live registry and current source before writing config.
- Treat a successful resolver test, public `/api/status`, visible picker row, or direct provider probe as partial evidence; verify the live Hermes request and its response shape.
- Make route changes staged and reversible by default; never silently change defaults, subscription scope, credentials, or billing behavior.
- Preserve canonical raw history and tool results in state storage; optimize only the provider prompt view.
- Keep stable payload blocks before volatile blocks, preserve tool-call/result pairing, and never send Anthropic cache markers to automatic-prefix providers.
- Distinguish model quality, endpoint reliability, tool/action success, latency, cache reuse, and cost per successful task; do not collapse them into one unsupported score.
- Restart or reset only the owner of cached code/config after inspecting process scope; a fresh picker or conversation does not imply a fresh gateway.

## Route the request class

### Model/provider family routing

1. Record the visible picker requirement separately from the runtime requirement.
2. Build a route table keyed by exact model family: endpoint/base URL, API mode, auth/header rules, request transformation, stream normalizer, and verification probe.
3. Pass the final normalized target model into resolution; provider-level mode is not enough for mixed catalogs.
4. Test one model per family with a red regression first, then run the live picker and outbound request.
5. Keep incompatible transports as separate runtime entries even when the presentation layer groups them.

### Delegated model routing

Treat `delegate_task` as a separate transport boundary. Verify whether the live schema accepts a route/model/provider field instead of assuming arbitrary arguments are forwarded. Prefer named, auditable routes or explicit profiles over hidden per-call mutation; reset the session when delegation config is cached. Verify pure resolver logic, runtime logs, and a real subagent canary independently.

### Tool/façade routing

Use one high-level façade for a user-facing capability when it exists. The orchestrator owns intent and semantic fields; the façade owns a small contract; backend routers own adapter choice, bounded fallback, and deterministic validation. Deferred tools require `tool_search → tool_describe → tool_call` when omitted from the active schema. Generic skills must delegate to a more specific façade rather than naming a backend directly.

## Catalog and picker operations

- Separate provider order, curated model list, live model catalog, plugin fallback list, cache state, and named-profile config.
- Treat reasoning labels such as `low/high/max` as settings unless the provider publishes distinct IDs; never invent sibling model IDs.
- When consolidating visible providers, map `(visible slug, model ID)` to the actual runtime provider before switching models.
- Verify YAML value types after writes; JSON-looking lists can persist as scalar strings.
- Check default and `include_unconfigured` picker payloads for duplicate/stale rows, then restart the owning gateway and reopen the TUI/Desktop picker.

## Payload, compaction, and cache operations

Layer payloads as stable static prefix, selected dynamic context, evidence pointers/digests, raw recent tail, and latest user message. Historical summaries and memory are reference-only and cannot create work. Keep the latest user message authoritative.

At provider assembly:

- retain exact raw ledger rows and render a copied prompt view;
- digest consumed large tool results, deduplicate repeated skill loads, and keep `state_db://` recall references;
- leave the first pending skill body readable once, then replace it with a deterministic digest;
- preserve assistant tool calls paired with tool results for every provider shape;
- measure role/token budgets, schema size, cache read/write tokens, exact recall, and provider acceptance from a real request dump.

Order stable tools/instructions before dynamic history and user content. Use explicit `cache_control` breakpoints only for providers that support them; automatic-prefix providers need a plain provider-native payload. Include cached input tokens when deciding whether compression should trigger.

## Verification workflow

1. Identify active profile, model, provider, API mode, toolset, working directory, and process owner.
2. Freeze a fresh-session baseline and capture the actual assembled request after middleware/transport conversion.
3. Verify catalog/picker visibility, resolved route, endpoint, request body, stream/tool-call pairing, auth scope, and usage/cost metadata.
4. Run an A/B with the same prompt, model, image/tools, warm/cold state, and timeout; report raw runs and tails.
5. Verify exact recall from state storage and that the raw ledger is unchanged after slimming.
6. Reset/restart only the required runtime, then repeat one end-to-end live smoke.

## Failure classifications

- Model absent: catalog/picker/config issue.
- Model visible but wrong endpoint: presentation/runtime mapping issue.
- Direct provider works but Hermes fails: request transformation, auth, stream, or route issue.
- Cache read frozen while input grows: breakpoint/TTL/payload-order issue.
- Tool schema present but not selected: deferred discovery or precedence issue.
- Unit tests pass but live request differs: stale process or untested middleware path.

## References and support

- `references/absorbed-source-routing.md` — mandatory routing to the exact original packages when detailed procedures are needed; do not retry removed names.

- `references/hermes-routing-and-payload.md` — compact route tables, provider/cache matrix, picker and validation checklists.
- Use archived package references for provider-specific recipes only when the compact class rules do not answer the question.
