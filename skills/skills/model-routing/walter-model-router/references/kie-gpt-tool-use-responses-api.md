# Kie.ai GPT Tool-Use — Responses API Format

This reference records a successful tool-use probe for one Kie GPT route. Treat
its call-ID behavior, latency, and cost as route-specific evidence, not as a
universal Astra contract.

Kie.ai's `codex/v1/responses` endpoint supports tool calling (function
calling) when using the **Responses API item format** — NOT the Chat
Completions message format.

## Working format (Responses API)

```json
{
  "model": "gpt-5-6-luna",
  "input": [
    {"role": "user", "content": "What is the weather in Paris?"},
    {"type": "function_call", "call_id": "fc_abc123", "name": "get_weather", "arguments": "{\"city\":\"Paris\"}"},
    {"type": "function_call_output", "call_id": "fc_abc123", "output": "{\"city\":\"Paris\",\"temp_c\":22}"}
  ],
  "tools": [
    {"type": "function", "name": "get_weather", "description": "...", "parameters": {...}}
  ],
  "tool_choice": "auto"
}
```

Key details:
- Tool calls use `"type": "function_call"` items with `call_id` starting with `fc_`
- Tool results use `"type": "function_call_output"` items
- Kie.ai issues call IDs as `call_xxx` — convert to `fc_xxx` by replacing the prefix
- Streaming works: tool calls come as `response.output_item.added` → `response.function_call_arguments.delta` → `response.output_item.done`
- Reasoning tokens are included as `type: "reasoning"` items (billed separately)

## Non-working format (Chat Completions)

```json
// ❌ This does NOT work on Kie.ai Responses endpoint:
{"role": "assistant", "tool_calls": [{"id": "call_xxx", "type": "function", "function": {...}}]},
{"role": "tool", "tool_call_id": "call_xxx", "content": "result"}
```

The Chat Completions format returns content but the model does not process
the tool result — it treats it as a regular message.

## Hermes integration

Use a dedicated active Hermes provider with `api_mode: "codex_responses"` and
`https://api.kie.ai/codex/v1`; do not attach a GPT model to a Kie provider bound
to Claude's Anthropic route. Hermes can convert its internal tool representation
to Responses items, but verify the active provider/profile and dry-run the final
payload because generic Codex extensions may not belong to the target Kie model.

## Performance

- Tool-use loop (3 tools, GPT-5.6 Luna): 19s, $0.0005 (vs $0.0032 on OpenRouter)
- Same task, same quality, 84% cheaper
- TTFB ~2s, streaming speed ~53 tok/s (vs 195 tok/s on OpenRouter)
- Kie.ai is 1.8× slower for tool-use loops but 84% cheaper

## Pitfall

The server occasionally returns "The server is currently being maintained"
(HTTP 200, non-streaming, JSON body with code 400). Retry with backoff.
