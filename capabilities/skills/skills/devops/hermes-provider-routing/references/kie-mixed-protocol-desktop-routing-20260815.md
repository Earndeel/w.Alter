# Kie.ai mixed-protocol provider routing

## Diagnostic pattern

When a consolidated picker selects a model but the outbound URL belongs to another model family, classify it as a runtime-routing failure before judging model capability. Compare the selected model, resolved provider, base URL, API mode, auth presence, request shape, response content type, and stream event count.

## Verified direct contract

The independent Kie probe used:

- endpoint: `https://api.kie.ai/grok/v1/responses`
- model: `grok-4-6`
- SSE Responses events including `response.output_item.added`, `response.function_call_arguments.delta`, `response.function_call_arguments.done`, and `response.completed`
- structured function call round-trip succeeded

Therefore the Hermes route must use the Responses transport, not Anthropic Messages or Chat Completions.

## Correct architectural rule

Keep one visible Kie.ai provider group if the user wants a consolidated picker, but route by model family at runtime:

| Family | Base URL | Hermes mode |
|---|---|---|
| `claude-*` | `https://api.kie.ai/claude` | `anthropic_messages` |
| `grok-*` | `https://api.kie.ai/grok/v1` | `codex_responses` |
| `gpt-6-astra` | `https://api.kie.ai/codex/v1` | `codex_responses` |

The Responses transport appends `/responses` to the configured `/v1` base. The request builder must classify each Kie Responses family correctly so tool conversion, reasoning limits, and stream normalization apply. Astra currently requires `stream=True`; treat non-streaming requests as incompatible until a fresh upstream probe changes that contract.

## Fix shape

1. Carry `target_model` into `_resolve_named_custom_runtime()`.
2. For an `api.kie.ai` endpoint, route `grok-*` to `https://api.kie.ai/grok/v1` and `gpt-6-astra` to `https://api.kie.ai/codex/v1`; set `api_mode=codex_responses` for both.
3. Add URL detection for `/grok` and `/claude` so direct/custom resolution does not fall back to `chat_completions`.
4. In the Responses request builder, treat `api.kie.ai/grok/v1` as `is_xai_responses` even though the runtime provider is `custom`.
5. For Claude’s Anthropic route, use Bearer authentication and a browser-like User-Agent; Kie’s WAF can reject SDK-default signatures.
6. Keep the consolidated provider's `models` value as a native YAML list. If the installed Hermes CLI serializes a dynamic provider list as a quoted scalar, use its atomic round-trip YAML updater for `providers.kie.models`, then read back both the type and exact model IDs.
7. For Astra, force `stream=True` in the Responses request path; do not rely on a non-streaming fallback while the upstream contract requires SSE.
8. After a backend source change, reload the long-lived Dashboard/gateway process before the Desktop test. A fresh Desktop session alone cannot load changed Python modules in an already-running backend.

## Regression coverage

The focused routing tests should assert:

- Grok target → `https://api.kie.ai/grok/v1` + `codex_responses`;
- Astra target → `https://api.kie.ai/codex/v1` + `codex_responses`;
- Claude target → `https://api.kie.ai/claude` + `anthropic_messages`.

A green resolver test is not enough for final acceptance. Follow with one fresh Desktop request and inspect the request dump or session billing metadata for the actual Kie URL and provider response. Never report the fix as live-validated until that step passes.

## Important correction to prior configuration approach

Keep presentation consolidation and protocol-family routing independent: adding Astra to `providers.kie.models` must preserve the model-family route and transport mapping. Do not introduce a sibling provider as a workaround for a different endpoint; the resolver must carry the target model and select the correct route inside the consolidated provider.
