# Wire payload audit and optimization prioritization

Use this reference when the complaint is high per-call input tokens, slow provider calls, weak cache reuse, or excessive fixed overhead even on a tiny user prompt.

## Evidence hierarchy

Keep these artifacts distinct:

1. **Actual failed request dump** — authoritative for that failed wire attempt only.
2. **Successful session database row** — authoritative for persisted model/provider, response text, provider usage, timestamps, and finish reason.
3. **Reconstructed successful body** — useful when request dumping was disabled, but must be labeled reconstructed.
4. **Source/config inspection** — proves intended routing, not that a live request used it.
5. **Focused integration tests** — prove composable stages, not a single live click-through.

Never describe a reconstructed payload as a captured wire body. Record provenance for each component, hashes, redaction policy, and the fields that remain uncertain.

## Reconstructing a successful Responses payload

When the successful call was not dumped:

- take the exact system prompt from the successful persisted session;
- take tool schemas from a temporally adjacent preflight dump only if the loaded tool set is demonstrably the same;
- run the actual transport `build_kwargs()` code offline with the successful model, user message, reasoning config, output budget, session ID, provider, and base URL;
- redact only secrets; keep non-secret headers such as `User-Agent` exact;
- serialize canonically and compute a SHA-256;
- store both the redacted payload and a compact metrics summary;
- state plainly that the artifact is reconstructed, not wire-captured.

## Measure both conversation and fixed overhead

A role-only `state.db` analysis is insufficient. Break the final provider body into:

- `instructions`;
- serialized `tools`;
- `input` / conversation;
- other JSON/request fields.

Measure both compact bytes and tokenizer estimates. Compare the tokenizer estimate with provider-reported `input_tokens`; use provider usage for billing totals and local tokenization only for component allocation.

Also report:

- number of tool schemas;
- top schemas by serialized size;
- skills-catalog token count inside instructions;
- user-input share;
- cache-read/write tokens;
- exact response latency from persisted timestamps or transport logs;
- whether cost telemetry has a real provider tariff.

## Prioritize by percent of total

Before implementing, quantify each proposal against the whole request, not only its local component.

Recommended order:

1. **Stop redundant calls first.** A compaction loop can dominate all token savings. Count historical calls/events that a corrected threshold would avoid.
2. **Lazy tool routing.** Keep a small direct core and make the rest discoverable on demand. Estimate savings by serializing the actual retained core. Preserve functionality and account for the extra discovery turn.
3. **Selective skill injection.** Replace the full catalog with a high-recall top-k shortlist plus `skills_list` fallback. Quantify expected catalog reduction and state the miss-risk.
4. **Prompt-cache contract test.** Compare reported cache reads with the theoretical reusable static prefix; verify provider support before changing payload shape.
5. **Tool-result prompt-view slimming.** Apply when persisted tool content, rather than fixed schemas/instructions, is measured as dominant.
6. **Micro-edits to prose/schema descriptions.** Deprioritize unless the preceding categories are already controlled.

## Cache-efficiency check

For a stable static prefix of approximately `S` tokens across `N` calls, a rough upper-bound reusable prefix is `S × (N - 1)`. Compare reported cache reads with this number, but label it theoretical: history rewrites, provider TTL, routing, and unsupported cache keys can invalidate it.

A `prompt_cache_key` present in the body proves only that Hermes sent a key. It does not prove the provider honored or billed the cache.

## Routing diagnosis

Separate presentation aliases from runtime provider IDs. A direct harness that instantiates an agent using a UI alias can bypass credential, base-URL, API-mode, and header resolution.

Before blaming Desktop or Gateway:

- trace the alias normalization function;
- test presentation alias → runtime provider mapping;
- inspect the actual URL, API mode, and authorization placeholder in the failed dump;
- compare with a successful runtime-provider session;
- determine whether the harness exercised the same construction path as production.

A 401/403 sent to the wrong endpoint with a missing-key placeholder is a harness/config-resolution failure, not evidence of gateway truncation.

## Cost reporting

Do not equate `estimated_cost_usd = 0` with free usage when provider pricing is absent. Report:

- provider-reported tokens;
- Hermes telemetry value;
- whether a Kie/reseller tariff is configured;
- optional upstream public list-price estimate, explicitly labeled as a reference rather than the reseller invoice.

## Deployment status vocabulary

Every fix should be labeled as one of:

- **written** — file/config changed;
- **validated** — tests or deterministic probe passed;
- **live** — the active long-running service loaded it.

Do not call a Python patch deployed before the service reloads it. Avoid restarting the service mid-response merely to satisfy wording; perform a controlled restart when deployment is explicitly in scope.