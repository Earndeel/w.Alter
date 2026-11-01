---
name: hermes-provider-routing
description: "Use when Hermes fronts multiple model-family endpoints."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [hermes, provider, routing, desktop, streaming, kie-ai, responses-api]
    related_skills: [hermes-provider-mastery, hermes-harness-auditing, provider-model-catalog-management]
---

# Hermes Provider Routing

Use this class-level skill when one visible Hermes provider or picker group fronts several upstream API families or protocol transports. Separate **presentation identity** from **runtime routing**: a consolidated picker must not force every model through one endpoint or wire format.

## When to Use

Use when one Hermes provider fronts multiple model-family endpoints, a Desktop model selection produces an empty or malformed stream, or a direct provider probe works while Hermes fails.

## Trigger

Load this skill when:

- a model appears in Desktop `/model` but fails only after selection;
- a named-profile session dies at init with `Unknown provider '<slug>'` after selecting a model that already works on default;
- a provider has Claude, Responses, Chat, or Gemini families behind different URLs;
- a voice/TTS provider is being added as an option alongside the current Walter provider;
- a stream is empty, malformed, or has no events;
- a direct API probe works but Hermes fails;
- a user asks to consolidate provider rows without losing model-specific transport behavior;
- a user asks to make the currently-running model/provider available on another Hermes profile.

## Core workflow

1. **Freeze the user-facing requirement.** Decide whether the request concerns visible picker grouping, runtime provider identity, or both. If Monsieur asks for one consolidated list, keep one presentation row; do not use a second visible provider solely as a transport workaround. For auxiliary media/TTS providers, distinguish the active/default provider from an explicitly selectable provider: adding `tts.providers.<name>` must not rewrite `tts.provider` unless Monsieur explicitly asks to switch Walter.
2. **Capture failing wire evidence before changing code.** Inspect request-dump or session evidence for model, URL, API mode, auth presence, headers, body shape, response status, and stream event count. A displayed model label is not proof of routing.
3. **Verify the direct upstream contract independently.** Use the exact endpoint, model ID, auth scheme, User-Agent, request shape, and SSE/JSON parser required by the provider. Preserve a redacted artifact when possible.
4. **Build a model-family route table.** Record model matcher, rewritten base URL, Hermes `api_mode`, auth/header requirements, request-body transform, and stream normalizer.
5. **Trace every runtime entry path.** Dynamic routing must cover initial agent construction, Desktop/gateway session creation, mid-session model switching, and auxiliary clients if they can call the same provider. Do not patch only the picker or one client constructor.
6. **Pass the final target model into resolution.** A provider-level `api_mode` and saved `base_url` are insufficient for a mixed catalog. Runtime resolution must receive `target_model` after aliases and normalization are finalized.
7. **Add a failing regression test first.** Assert the exact route and transport for one model in each family. Run it red, implement the smallest routing change, then run it green.
8. **Verify the transport-specific request builder.** For Responses families, confirm tool conversion, reasoning fields, model-specific schema sanitization, and endpoint classification. For Anthropic Messages, confirm `Authorization: Bearer` where required and avoid accidental `x-api-key` or OAuth injection.
9. **Reload the long-lived backend.** Source changes are not loaded by merely opening a new Desktop conversation if the Dashboard/gateway process already imported old modules. Inspect process ownership and cgroup before restart; never broadly kill unrelated user processes.
10. **Verify the live picker payload before changing routing again.** Call the active `build_models_payload()` path or authenticated `/api/model/options` and inspect the target provider's `slug`, `models`, `source`, and `api_url`. If the target model is present there but absent in Desktop, treat it as a client-side cache/state problem and refresh or reopen the picker; do not create another provider slug.
11. **Perform one fresh Desktop smoke test.** Inspect the actual outbound URL and response or billing metadata. A green resolver test or visible picker entry alone is not live validation.

## Kie.ai reference route

Kie’s consolidated group can be one picker row while routing families independently:

| Family | Base URL | Hermes mode |
|---|---|---|
| `claude-*` | `https://api.kie.ai/claude` | `anthropic_messages` |
| `grok-*` | `https://api.kie.ai/grok/v1` | `codex_responses` |
| `gpt-6-astra` | `https://api.kie.ai/codex/v1` | `codex_responses` |

The Grok Responses endpoint is `https://api.kie.ai/grok/v1/responses` (the OpenAI SDK appends `/responses`, so the configured base must already include `/v1`). Astra uses the same Responses transport family at `https://api.kie.ai/codex/v1/responses`; the current Kie Astra contract requires `stream=True`, so enforce streaming at the route/request-builder layer. A direct verified probe emitting structured Responses SSE events proves the upstream contract; an empty Hermes stream after a request to another family's endpoint is a routing/protocol mismatch, not a model capability verdict.

Live presentation identity for that mixed catalog is the named custom provider `providers.kie` (`model.provider: custom:kie`), not a sibling slug. Add the exact `gpt-6-astra` ID to that provider's `models` list and route it to `https://api.kie.ai/codex/v1` with `codex_responses`; do not create `kie-astra` or revive `kie-gpt` merely to obtain a different transport. Runtime `resolve_runtime_provider` rewrites each model family from the shared Kie base URL.

Kimi may remain a separate runtime entry such as `providers.kie-kimi` when its base URL or `api_mode` differs from the main Kie group; that separation protects the wire contract, not the vendor identity. If Monsieur explicitly wants one visible Kie folder, merge the rows in the Desktop presentation layer and translate Kimi model selections back to `kie-kimi` at switch time instead of forcing Kimi through the Claude/Astra route.

For Kie Anthropic-compatible traffic, use Bearer auth and a browser-like User-Agent when required by the upstream WAF. Preserve user-configured headers and never print credentials.

## Evidence standards

Classify claims explicitly:

- **MEASURED:** captured request, live response, focused test, or session billing row;
- **OBSERVED IN CODE:** route or transport behavior read from source;
- **UNKNOWN:** not yet proven by a fresh Desktop request.

Do not say “fixed” when only a unit test passes. Say “resolver fixed; live Desktop validation pending” until the backend has been reloaded and the request has been observed on the correct upstream route.

## Pitfalls

- **One picker row ≠ one endpoint.** Presentation consolidation must not erase model-family routing.
- **`provider=custom` can hide the real configured provider.** Inspect saved provider identity, resolved endpoint, and target model together.
- **Provider-level `api_mode` is not enough.** It may be correct for Claude and wrong for Grok or Astra in the same Kie block.
- **Keep dynamic model lists native.** Read back `providers.<name>.models` as a YAML list after writing it. On Hermes versions whose CLI treats dynamic provider keys as scalar values, a JSON-looking `hermes config set` value can become a quoted string; use Hermes' atomic round-trip YAML updater for that single path, then re-read the type and contents.
- **Named profiles isolate `providers:`.** A custom slug that works on default is invisible to another profile's config. Desktop can still offer `grok-4-6` and write `provider: kie`; init then fails with `Unknown provider 'kie'` if that profile lacks the shared `providers.kie` block.
- **Copy the live slug — do not invent a sibling.** If the working session is `custom:kie` / `providers.kie`, copy that exact block. Do not create `kie-grok`, `kie-astra`, or `kie-gpt` as transport workarounds; family routing already rewrites the model to its endpoint.
- **Selection ≠ default.** Adding the provider makes the model selectable. Do not change `model.default` unless asked to switch the orchestrator.
- **Additive TTS means additive.** For `tts.providers.<name>` command/plugin entries, preserve the existing `tts.provider`; only set it to the new provider after an explicit switch request. Do not infer a platform-specific delivery format such as Opus from `voice_compatible`; keep the requested provider container and verify the generated artifact.
- **Make-it-available is a config copy, not a diagnosis.** When asked to make the current model usable on a profile, patch that profile in the same turn; do not stop after explaining the missing slug.
- **Direct probes do not prove Hermes routing.** They establish the upstream contract only; capture Hermes’ outbound URL separately.
- **Empty stream is not a capability result.** First check wrong path, wrong auth, wrong content type, missing browser UA, and parser expectations.
- **Fresh Desktop session does not imply fresh backend code.** Long-lived Python services retain imported modules until a controlled reload.
- **Live picker payload beats the visible stale list.** If `/api/model/options` or `build_models_payload()` contains the exact model under the expected slug, refresh/reopen the client before changing provider configuration; the UI can cache the catalog independently.
- **Same vendor does not mean same runtime contract.** Keep a Kimi-like entry separate when its URL or `api_mode` differs, and consolidate only the presentation row with an explicit model-to-provider switch map.
- **Do not silently substitute a nearby model or fallback provider.** Keep the requested ID attached to every diagnostic.

## References

- `references/kie-mixed-protocol-desktop-routing-20260815.md` — Kie route table, direct SSE contract, and regression checklist.
- `references/desktop-provider-route-evidence.md` — compact evidence format for Desktop request/session proof.
- `references/named-profile-custom-provider-copy.md` — copy a working named custom provider into an isolated profile without inventing a new slug.
