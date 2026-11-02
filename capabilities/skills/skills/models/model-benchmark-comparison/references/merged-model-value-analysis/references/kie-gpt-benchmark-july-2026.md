# GPT-5.6 Luna — Kie.ai vs OpenRouter Benchmark (July 2026)

Live benchmark comparing GPT-5.6 Luna on Kie.ai vs OpenRouter (API pricing = Codex equivalent). Same complex agentic task on both endpoints.

## Results (2026-07-26)

| Métrique | OpenRouter (API) | Kie.ai | Ratio |
|---|---|---|---|
| TTFB | 4.8s | 2.1s | 0.4× |
| Temps total | 21s | 84s | 3.9× |
| Output tokens | 4,096 | 4,506 | 1.1× |
| Output chars | 16,842 | 18,446 | 1.1× |
| Coût | $0.0247 | $0.0076 | −69% |
| Reasoning tokens | 0 | 507 | — |

## Key Findings

- **Kie.ai 69% cheaper** — matches the 72% theoretical reduction (API: $1/$6 per M, Kie: $0.28/$1.68)
- **Kie.ai 3.9× slower** — 84s vs 21s. Proxy Java infrastructure + queue delay. TTFB is actually faster (2.1s vs 4.8s) but token generation throughput is much lower
- **Quality comparable** — same output structure, same analysis depth. Kie.ai generates slightly more tokens (reasoning blocks included)
- **Kie.ai adds reasoning** — 507 reasoning tokens generated internally (included in price), OpenRouter chat completions API doesn't return reasoning

## Endpoint Quirks Discovered

### Kie.ai GPT Transport
- Endpoint: `POST https://api.kie.ai/codex/v1/responses`
- `input` must be a **string** (not array of messages) — sending `[{role, content}]` returns 500
- **Browser User-Agent mandatory**: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36`
- Always returns SSE (streaming) regardless of `stream` parameter
- `input_tokens` reported as 0 in usage — bug, use char-based estimation
- `reasoning.effort`: `"low"`, `"medium"`, or `"high"` — reasoning tokens included in `output_tokens_details.reasoning_tokens`

### Codex API (chatgpt.com)
- Endpoint: `POST https://chatgpt.com/backend-api/codex/responses` (no `/v1`)
- `input` must be an **array** of `{role, content}` — sending a string returns 400
- Requires `"store": False` and `"stream": True` in payload
- **GPT-5.6 Luna/Sol/Terra BLOCKED** — returns "not supported when using Codex with a ChatGPT account"
- Token refresh: `POST https://auth.openai.com/oauth/token` with `client_id: app_EMoamEEZ73f0CkXaXp7hrann`

### OpenRouter
- Model ID uses **dots**: `openai/gpt-5.6-luna` (NOT `openai/gpt-5-6-luna`)
- `/models` endpoint returns dash format but API rejects it — always convert to dots
- Pricing matches official OpenAI API ($1/$6 per M for Luna)

## Script

See `/tmp/bench_final.py` for the runnable one-shot benchmark script.

---

# GPT-5.6 Luna — Tool-Use Benchmark (July 2026)

Live agentic tool-use comparison: same 3-tool debugging task (search_docs → read_file → run_tests) on both endpoints.

## Tool-Use Results (2026-07-26)

| Métrique | OpenRouter (Chat API) | Kie.ai (Responses API) | Ratio |
|---|---|---|---|
| Temps total | 10s | 19s | 1.8× |
| Input tokens | 1,140 | 0 (Kie bug) | — |
| Output tokens | 342 | 313 | 0.9× |
| Tool calls réussis | 3/3 | 3/3 | ✅ |
| Coût | $0.0032 | $0.0005 | **−84%** |

## Key Findings

- **Kie.ai tool-use works perfectly** — 3/3 function calls executed, correct format, no errors
- **84% cheaper in tool-use** — even more savings than text-only (69%) because growing tool-use context is billed at Kie.ai's cheaper rates
- **Only 1.8× slower** for tool-use vs 3.9× for text-only — smaller payloads per turn, less proxy overhead
- **Call ID conversion required**: API returns `call_xxx`, must convert to `fc_xxx` for replay. Without this, `function_call_output` items are silently ignored.
- **Format is Responses API, NOT Chat Completions**: tool calls use `{"type": "function_call", "call_id": "fc_...", ...}` and `{"type": "function_call_output", ...}` — Hermes' `agent/codex_responses_adapter.py` handles this conversion automatically for the `kie-gpt` provider.

## Combined Economics

| Scenario | Kie.ai vs API | Speed penalty |
|---|---|---|
| One-shot text (4K tokens) | −69% | 3.9× |
| Tool-use agentic (3 tools) | −84% | 1.8× |
| Multi-turn agentic (10+ tools) | >−84% (estimated) | ~2× |

**Bottom line:** Kie.ai is perfectly viable as an agentic backend. The cost savings grow with complexity, and the speed penalty shrinks. For autonomous multi-step agents where you're not waiting interactively, the tradeoff is extremely favorable.

## Tool-Use Format Reference

For the exact Responses API format and multi-turn conversation structure, see the `kie-ai-api-direct` skill §7. The critical format differences from Chat Completions:

| Concept | Chat Completions | Responses API (Kie.ai GPT) |
|---|---|---|
| Tool declaration | `{"type":"function","function":{...}}` | `{"type":"function","name":"...","parameters":{...}}` |
| Tool call | `{"role":"assistant","tool_calls":[...]}` | `{"type":"function_call","call_id":"fc_...",...}` |
| Tool result | `{"role":"tool","tool_call_id":"..."}` | `{"type":"function_call_output","call_id":"fc_...",...}` |
| Call ID prefix | `call_xxx` | `fc_xxx` (must convert!) |
| Message list | `messages` array | `input` array (mixed items) |
