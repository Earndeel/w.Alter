---
name: kie-ai-provider-mastery
description: Kie.ai provider — endpoints, tool-use, Cloudflare, pitfalls.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [kie.ai, claude, provider, tool-use, anthropic, codex]
---

# Kie.ai Provider Mastery

Complete operational knowledge for Kie.ai (https://kie.ai) — the discounted LLM proxy behind Cloudflare. Covers Claude models via Anthropic Messages endpoint, GPT models via Responses endpoint, tool-use formats, pricing, and Cloudflare bypass.

## When to Use

Use when configuring, debugging, or benchmarking Kie.ai providers in Hermes. Also when making direct API calls to Kie.ai endpoints. For model-specific Codex/Responses contract discovery and schema extraction, see `references/kie-codex-endpoint-contract.md`. For cache diagnosis in the unified Kie/Grok Desktop route, see `references/grok-hermes-cache-investigation-20260815.md`.

## Provider Endpoints

| Provider | Endpoint | Format | Models |
|---|---|---|---|
| `kie` (Claude) | `https://api.kie.ai/claude/v1/messages` | Anthropic Messages | claude-opus-5, opus-4.8, opus-4.7, sonnet-5, fable-5 |
| dedicated `kie-gpt` / `kie-astra` entry | `https://api.kie.ai/codex/v1/responses` | OpenAI Responses | gpt-5-6-luna, gpt-5-6-sol, gpt-6-astra (resolve live) |

### Pricing (always verify live Kie.ai pages)

Kie.ai pricing is dynamic and model-specific. Do not use a family-average discount or
carry the static numbers below into a benchmark. The deterministic AA + Kie collector
(`aa-pareto-model-optimizer`) fetches the public pages and keeps Kie’s exact rates,
marketing claim, official-price comparison, and AA-reference comparison separate.

Observed live page evidence on 2026-07-31:

| Model | Kie.ai page | Kie input / 1M | Kie output / 1M | Evidence status |
|---|---|---:|---:|---|
| GPT-5.6 Luna | https://kie.ai/gpt-5-6 | $0.056 | $0.336 | exact rates; page claim conflicts with computed official comparison |
| Grok 4.5 | https://kie.ai/grok-4-5 | $0.80 | $2.40 | exact rates; no Kie official baseline exposed |
| Claude Opus 5 | https://kie.ai/claude-opus-5 | — | — | page exists; `Pricing: wocx`, unverified |

A Kie page being present proves availability, not that a public token price is
available. Report `unverified` for pages such as Claude Opus 5 rather than inferring
a discount from another Claude model.

## Model discovery and contract discipline

- Resolve the exact model ID against the protocol-specific catalog before calling it: `GET https://api.kie.ai/codex/v1/models` for the Codex/Responses family, with Bearer authentication and a browser-shaped `User-Agent`. A model appearing in the catalog proves visibility/authentication, not that a valid generation request is currently operational.
- Treat the official model page as the source of truth for the target model's request schema. Do not copy fields, reasoning values, tool-loop IDs, or defaults from another GPT/Grok route. If the rendered page hides nested fields, use the reusable Apidog extraction recipe in `references/kie-codex-endpoint-contract.md`.
- Set ambiguous controls explicitly. In particular, send `stream` explicitly and branch on the returned `Content-Type`; Kie documentation can disagree between prose, JSON Schema defaults, and response media types.
- Keep a valid generation smoke test separate from discovery: it may consume credits. Cap paid probes and get approval before sending one; otherwise report catalog access and documentation evidence without claiming successful inference.

## Cloudflare Bypass (CRITICAL)

Kie.ai sits behind Cloudflare which blocks requests without a browser-shaped User-Agent.

### Direct API calls (Python)

```python
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
headers = {"User-Agent": UA, "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
```

### In Hermes — provider-specific routing and User-Agent

Kie’s Cloudflare edge can reject the default SDK signature. Treat the browser-shaped `User-Agent` as part of the provider contract and verify it in the resolved runtime, not only in `config.yaml`.

Never add a Codex/Responses model to a provider whose base URL and `api_mode` are bound to another model family (for example Claude + `/claude` + `anthropic_messages`). Create a separate named provider with `api: https://api.kie.ai/codex/v1`, `api_mode: codex_responses`, `key_env: KIE_API_KEY`, the exact model ID, and an explicit browser-shaped `extra_headers` entry.

`kie-gpt` may be implemented as a plugin or as a named custom config entry; a picker label, historical backup, or test file does not prove it exists in the active Hermes tree. Verify provider resolution, final URL, API mode, and headers before using it.

### Kie.ai latency

Kie.ai adds 2-15s of overhead due to its Java proxy queue. GPT models via the Responses endpoint are slower (19-84s for complex tasks) than direct API (10-21s). Claude models via the Anthropic endpoint are faster (3-9s) due to more efficient streaming.

## Reasoning and probe interpretation

For mixed-protocol Kie probes, separate visible output, provider-reported reasoning counters, and actual tool use. `reasoning_tokens`/`thinkingTokenCount` are opaque usage metrics, not exposed chain-of-thought; zero is an observation, not proof of no internal reasoning. A no-tools prompt cannot test tool capability: inspect protocol events and server-side counters, then run a dedicated probe with a tool schema. Detailed signatures and reporting rules are in `references/reasoning-and-tool-call-probes.md`.

## Hermes Codex/Responses admission gate

Before promoting a Kie GPT model to a W.Alter route, follow this order:

1. Resolve the exact model ID against `GET https://api.kie.ai/codex/v1/models`; treat HTTP 200 as catalog visibility/authentication only.
2. Inspect the active Hermes provider entry and ensure it is separate from Claude/Gemini entries; confirm `api_mode: codex_responses`, the `/codex/v1` base URL, the Bearer key mapping, and the browser-shaped User-Agent.
3. Run a local transport dry-run before spending credits. Inspect `ResponsesApiTransport().build_kwargs(...)` and compare every emitted field with the target Kie model page. Do not assume that generic Codex fields such as `store`, `include`, cache keys, `parallel_tool_calls`, `reasoning.summary`, or `instructions` are accepted.
4. If the dry-run emits undocumented fields, add a provider-specific filtering/profile layer; do not silently broaden the target contract from another Kie model.
5. Send `stream` explicitly and parse the actual `Content-Type`; keep streaming, function calling, call-ID normalization, and non-stream response parsing as separate probes.
6. Only after the payload contract is clean, run one approved valid generation smoke test. Record its HTTP result, application-level error envelope, latency, usage, and billing separately from the catalog result.

Before the contract gate, keep an unproven model secondary and cap paid probes. After the gate, do not reject Kie solely because it is a proxy or has transient 500s: if the measured effective cost after retries/fallback remains lower, promote it as the primary route for safe workload classes and keep OpenAI as a circuit-breaker fallback. Keep each unverified feature class (tool loops, web access, native computer use, strict structured output) secondary until its own probe passes. The full schema extraction and contradiction checklist remain in `references/kie-codex-endpoint-contract.md`.

### Cost-aware promotion

Use the following decision order instead of treating direct OpenAI as the only acceptable primary:

1. Keep the direct OpenAI provider intact; add Kie Astra as a separate provider with its own base URL, API mode, model ID, headers, and billing evidence. Never overwrite the OpenAI route or infer provider identity from a model label.
2. Measure effective cost per successful turn, including Kie credits, retry attempts, fallback calls, and failed-turn waste. A lower nominal token price is useful only when this adjusted cost remains lower.
3. Route ordinary text, reasoning, and coding turns to Kie once the minimal generation contract is stable. Keep OpenAI as the fallback for provider outages and contract failures.
4. Gate side-effecting tools separately. Do not automatically retry or fall back after a function call may have executed unless the operation is idempotent or its completion state is known.
5. Classify HTTP 500s before changing the route: maintenance/overload calls for bounded backoff and circuit breaking; an application-level `code: 500` with a completed HTTP response usually requires payload filtering or protocol correction.
6. Treat marketing capabilities on the Astra page (function calling, web access, reasoning levels, streaming, or computer use) as capability claims until the exact API schema and a live end-to-end probe confirm each one; do not generalize a successful Luna or Grok probe to Astra.

## Reporting format

For Kie endpoint reviews, use complete normal Markdown when it improves clarity: headings, decision tables, lists, inline JSON, and individually fenced code blocks are allowed. Never put the entire report inside one code fence, raw-text/preformatted wrapper, or artificial quote block; a display problem is not a reason to remove useful structure. Separate verified live facts, documentation claims, inferences, and unverified fields explicitly.

## Tool-Use Formats

### Grok 4.6 Responses (verified direct loop)

For `POST https://api.kie.ai/grok/v1/responses`:

- Define a function tool as `{"type":"function","name":"...","description":"...","parameters":{...}}`.
- For a deterministic capability probe, use `tool_choice: {"type":"function","name":"<tool>"}`. On the tested route, `tool_choice: "required"` was accepted but led to prose describing the call rather than a structured call; count a tool call only after observing `response.function_call_arguments.delta` and a completed `function_call` output item.
- Parse the full SSE sequence through `response.completed`; arguments arrive after `response.output_item.added`, not in the initial event.
- Send the exact returned `call_id` unchanged in the next-turn `function_call` and `function_call_output` items. Do not blindly apply the `fc_` rewrite used by the Codex route below: Grok returned `call-...` and accepted it unchanged in the verified loop.
- Web search and custom function tools are mutually exclusive on this endpoint.

Observed successful loop: Grok emitted `get_current_weather({"location":"Bangkok, Thailand","unit":"celsius"})`; a local deterministic tool returned `31°C, partly cloudy`; the second Kie call returned exactly `31°C, partly cloudy.` HTTP 200 on both turns, 0.11 + 0.05 credit. Redacted artifacts: `/tmp/kie-grok-tool-probe-v3/step1.raw_sse.txt`, `step2.raw_sse.txt`, `step1.summary.json`, `step2.summary.json`. A reusable condensed reference is `references/grok-tool-loop-verification.md`.

### Responses API (kie-gpt — GPT models)

Uses `type: function_call` / `function_call_output` items in the `input` array. CRITICAL for the **Codex** endpoint: call_ids must use the `fc_` prefix, not `call_`.

```python
# Assistant tool call (in input array)
{"type": "function_call", "call_id": "fc_XyZ123", "name": "search", "arguments": '{"query":"test"}'}

# Tool result (in input array, right after the function_call)
{"type": "function_call_output", "call_id": "fc_XyZ123", "output": '{"results": [...]}'}
```

The Codex API may return call_ids with `call_` prefix (e.g. `call_8QQrslXcbNbb9FokEljysK7T`); convert to `fc_` only for that route: `fc_id = f"fc_{call_id[5:]}"`.

### Anthropic Messages (kie — Claude models)

Standard Anthropic tool-use format:

```python
# Tool result
{"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use["id"], "content": result_json}]}
```

## Pitfalls

1. **Cloudflare 403**: Always send browser User-Agent. The `kie` provider in config.yaml does NOT do this — it needs a plugin or proper `default_headers` support in Hermes.
2. **Hermes Grok route base URL needs `/v1`.** The OpenAI SDK appends `/responses` to the custom-provider base URL, so configure `https://api.kie.ai/grok/v1` (not `.../grok`) — `/grok/responses` returns HTTP 404 `No message available`. Verified live 2026-08-15: grok-4-6 through Hermes `custom:kie` resolves to `api.kie.ai/grok/v1` + `codex_responses`, returns text and tool calls (sess. 20260815_123540_bb93be).
3. **Reasoning effort: Kie Grok rejects non-standard values.** `reasoning.effort: "max"` (or `xhigh`, carried over from a GPT-5.6 picker selection) returns HTTP 400 `Invalid reasoning effort.` In Hermes, `api.kie.ai/grok` must be detected as `is_xai_responses` (match the `/v1` suffix too), so effort is clamped to low/medium/high and omitted entirely for grok-4-6 (not in the xAI effort allowlist). Verified 2026-08-15: `--reasoning max` returns KIE_GROK_OK.
4. **Cache diagnosis:** Inspect Hermes `agent.log`, request dumps, and `state.db` rather than claiming access to Kie’s internal dashboard logs. Check URL `/grok/v1/responses`, stable `extra_body.prompt_cache_key`, stable `x-grok-conv-id`, and per-call `cached_tokens/input_tokens`. A zero cache read after tool/skill/schema changes is expected; `cache_write_tokens=0` is unknown, not proof of disabled writes. See `references/grok-hermes-cache-investigation-20260815.md`.
4. **fc_ prefix**: Responses API call_ids returned as `call_xxx` MUST be converted to `fc_xxx` for the function_call_output item. Without this, the model ignores the tool result.
5. **Streaming**: Kie.ai streams Claude responses efficiently (3-9s). GPT Responses API streams are slower (10-19s for tool-use loops) due to the Java proxy.
6. **Input token reporting**: The Responses API often reports `input_tokens: 0` — this is a Kie.ai quirk, not a real zero. Estimate from (prompt_length / 4).
7. **`/v1/chat/completions`**: This endpoint does NOT exist for Claude models on Kie.ai. Use `/claude/v1/messages` (Anthropic) or `/codex/v1/responses` (Responses).

## Verification

```bash
# Test Claude Opus 5 via Kie.ai Anthropic endpoint
python3 -c "
import requests, json, os
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36'
r = requests.post('https://api.kie.ai/claude/v1/messages',
  headers={'Authorization': f'Bearer ' + os.environ['KIE_API_KEY'], 'Content-Type': 'application/json', 'User-Agent': UA},
  json={'model': 'claude-opus-5', 'max_tokens': 50, 'messages': [{'role': 'user', 'content': 'Say OK'}]})
print(r.json()['content'][0]['text'])
"
```
