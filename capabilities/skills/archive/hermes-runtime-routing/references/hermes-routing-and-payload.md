# Hermes routing and payload reference

## Mixed-provider route table

Record each family as a row before changing a provider:

| Field | Required evidence |
|---|---|
| Visible provider/row | Exact picker slug, label, and model IDs |
| Runtime owner | Actual configured provider/profile |
| Model family | Exact ID/alias after normalization |
| Endpoint and API mode | Live outbound URL and wire protocol |
| Auth/header contract | Redacted header names and scope |
| Request transform | Tool, reasoning, stream, and content-shape conversion |
| Response proof | Event count, parser result, usage/cost metadata |
| Reload boundary | Gateway, TUI/Desktop, session reset, or next process |

Presentation consolidation is safe only when the mapping from visible row/model to runtime provider is explicit and tested. Do not merge incompatible Anthropic, Chat Completions, Responses, or Gemini transports merely because a vendor name matches.

## Catalog/picker checklist

1. Verify the exact model ID against the provider catalog.
2. Separate base model from reasoning setting.
3. Update curated list, fallback list, and profile config only where each is authoritative.
4. Read back parsed YAML types and both configured/unconfigured picker payloads.
5. Clear only the relevant cache, restart the owner, reopen the picker, and inspect the live payload.

## Delegation and façade checklist

- Inspect the live `delegate_task` schema and handler; arbitrary `model`/`provider` keys may be ignored.
- Prefer named routes with explicit model/provider pairs or isolated profiles.
- Verify route resolution in pure code, then logs, then a real subagent canary.
- Keep high-level façade selection in the orchestrator; keep adapter selection and semantic validation deterministic.
- Use deferred discovery only when the tool is absent from the active schema; `tool_describe` does not itself make a tool preferred.

## Payload/cache matrix

| Provider family | Cache control | Payload invariant |
|---|---|---|
| Anthropic-compatible | Explicit `cache_control` breakpoints, bounded count/TTL | Stable blocks before volatile; markers only on supported content blocks |
| OpenAI/MiMo/DeepSeek auto-prefix | No Anthropic markers | Stable serialized prefix and provider-native string/block shape |
| Gemini context cache | Separate cached-content API/ID | Follow provider cache lifecycle, not Anthropic headers |
| Responses/Codex | Provider-specific input/tool conversion | Keep dynamic input after stable tools when prefix caching depends on order |

Measure cache reads, writes, non-cached input, total provider input, and compressor thresholds from the real response. A low `prompt_tokens` value can omit cached tokens; include cache-read and cache-create fields when deciding whether compression should fire.

## Wire validation checklist

- Capture the request after middleware, provider conversion, and cache insertion.
- Normalize Chat Completions `messages`, Responses `input`, and Anthropic `system`/content blocks before comparing roles.
- Count logical tool calls/results and confirm protocol pairing.
- Compare raw ledger bytes/hashes with the prompt-view digest; exact recall must return the original.
- Run two similar turns in one fresh session for cache reuse, then one end-to-end tool call.
- Report the actual route, model, warm/cold state, token/cost fields, and unverified layers.
