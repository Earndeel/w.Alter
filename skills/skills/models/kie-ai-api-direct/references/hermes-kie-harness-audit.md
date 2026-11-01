# Hermes Kie Harness Audit — Desktop → Gateway → Agent → DB

Session-specific evidence captured 2026-07-13. This reference corrects an earlier audit that falsely attributed a direct-harness failure to the Desktop provider label.

## Correct architecture

```text
Desktop model picker
  presentation group: kie
        │ prompt/session JSON-RPC
        ▼
tui_gateway/server.py
  normalize presentation provider: kie → kie-gpt
  build runtime model config
        ▼
Hermes runtime provider plugin
  provider_id: kie-gpt
  api_mode: codex_responses
  base_url: https://api.kie.ai/codex/v1
  API key env: KIE_API_KEY
  browser User-Agent default header
        ▼
Responses transport
  POST https://api.kie.ai/codex/v1/responses
        ▼
normalized assistant response + usage persistence in state.db
```

The Desktop uses the presentation alias `kie`; the gateway is responsible for converting it to runtime provider `kie-gpt`. There is no evidence that the Desktop sends `kid`.

## Two sessions with different construction paths

| Field | Direct bypass harness (failed) | Runtime-provider harness (succeeded) |
|---|---:|---:|
| Session | `20260713_113013_8f4efa` | `20260713_113117_feffc8` |
| `model_config.provider` | `kie` | `kie-gpt` |
| Outbound path | `/claude/chat/completions` | `/codex/v1/responses` |
| Authorization | `Bearer None` | resolved `KIE_API_KEY` |
| `billing_provider` | `NULL` | `kie-gpt` |
| `billing_base_url` | `NULL` | `https://api.kie.ai/codex/v1` |
| `api_call_count` | `0` | `1` |
| Provider usage | `0 / 0` | `21,475 input / 8 output` |
| Result | HTTP 403 | exact `KIE_SOL_OK`, `finish_reason=stop` |
| User→assistant latency | no assistant response | 5.198 seconds |

### What the failed session proves

The failed harness instantiated the agent directly with presentation alias `provider="kie"`. That bypassed the production gateway normalizer, so it did not resolve the Kie GPT provider plugin, Responses API mode, or API-key environment variable.

The captured request dump showed:

- wrong URL: `https://api.kie.ai/claude/chat/completions`;
- `Authorization: Bearer None`;
- complete system prompt, user input, and 37 tool schemas;
- compact body size about 102.8 kB.

Therefore it proves a **harness construction failure**, not Desktop/Gateway truncation or corruption.

### What the successful session proves

The runtime-provider harness reached `https://api.kie.ai/codex/v1`, produced the exact requested assistant text, persisted non-zero provider usage, and recorded `billing_provider=kie-gpt`.

It proves the downstream plugin → transport → provider → normalizer → DB chain. Combined with focused Desktop and gateway tests, it validates the composed path; it is not a literal post-fix mouse-click wire capture.

## Source/runtime validation

The gateway and Desktop Kie source files predated the running dashboard service start, so those routing changes were loaded by the service inspected during the audit.

Validated suites included:

- 39 focused model-switch/gateway tests;
- 14 Desktop model-picker/status tests;
- Kie Responses transport tests;
- Desktop typecheck.

Do not claim a full click-through E2E unless one request is initiated by the actual Desktop selection and wire-captured through persistence.

## State database verification

```sql
SELECT id, model, model_config,
       billing_provider, billing_base_url,
       api_call_count, input_tokens, output_tokens,
       cache_read_tokens, cache_write_tokens,
       estimated_cost_usd, end_reason
FROM sessions
WHERE id = '<session_id>';
```

Interpretation:

- `model_config.provider` describes stored selection/config; it is not sufficient route proof.
- `billing_provider` and `billing_base_url` are strong evidence only after a successful provider call.
- `api_call_count=0` does not mean no HTTP retry occurred; the failed harness retried the 403 while persisting zero successful calls.
- `end_reason=ws_orphan_reap` is ambiguous and can appear on both successful and failed harness sessions.

## Billing and observability gaps

- `estimated_cost_usd=0` for Kie because Hermes lacks a Kie tariff. This is **unknown cost**, not proof of free usage.
- Preserve provider-reported usage and label any upstream public list-price calculation as an estimate, not the Kie invoice.
- Classify 401/403 as non-retryable after confirming the request has passed credential/provider resolution; otherwise retries obscure a deterministic configuration failure.
- Use distinct end reasons for provider failure, successful completion, and websocket orphan cleanup.

## Verification discipline

1. Test `kie → kie-gpt` normalization directly.
2. Test runtime model-config persistence.
3. Inspect the actual URL, API mode, headers, and body before blaming a UI layer.
4. Compare failed-request dumps with successful persisted billing metadata.
5. Distinguish direct bypass harnesses from production gateway construction.
6. Label reconstructed successful payloads as reconstructed when wire dumping was disabled.
