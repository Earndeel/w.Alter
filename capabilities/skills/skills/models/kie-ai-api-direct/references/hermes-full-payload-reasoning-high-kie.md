# Full Hermes payload replay to Kie Claude Sonnet 5 — reasoning high

Validated: 2026-07-01

## Scenario

User asked to send a **real Hermes payload** to `claude-sonnet-5` via Kie, not a small direct connectivity prompt. The goal was to verify whether Hermes' Anthropic Messages path actually forwards `thinking` / high reasoning settings and whether Kie returns visible thinking.

## Probe shape

Instantiate `AIAgent` directly from `~/.hermes/hermes-agent/run_agent.py` with:

- `provider='kie'`
- `base_url='https://api.kie.ai/claude'`
- `api_mode='anthropic_messages'`
- `model='claude-sonnet-5'`
- `reasoning_config={'enabled': True, 'effort': 'high'}`
- `skip_context_files=False`, `skip_memory=False`, `load_soul_identity=True`
- proxy `agent._anthropic_client.messages.stream` to capture the exact kwargs sent on the wire.

This captures the real runtime request created by Hermes, including system prompt, memory/context, message payload, and tool schemas.

## Observed request

The wire method was:

```text
anthropic.messages.stream
```

Top-level request keys:

```text
max_tokens, messages, model, output_config, system, thinking, tool_choice, tools
```

Important fields:

```json
{
  "model": "claude-sonnet-5",
  "max_tokens": 128000,
  "thinking": {"type": "adaptive", "display": "summarized"},
  "output_config": {"effort": "high"},
  "tool_choice": {"type": "auto"}
}
```

Payload size/shape from the probe:

- `system_blocks`: 1
- `system_chars`: 34455
- `messages_count`: 1
- `tools_count`: 37
- first tools included `browser_back`, `browser_click`, `browser_console`, `cronjob`, `delegate_task`, `execute_code`, `memory`, `patch`, `read_file`, `search_files`, etc.

## Observed response

Kie returned a valid Anthropic message:

```text
id=msg_01Y2SpLKojCxFACFGSa2oa3Q
model=claude-sonnet-5
stop_reason=end_turn
```

Usage excerpt:

```json
{
  "cache_creation": {"ephemeral_1h_input_tokens": 22842, "ephemeral_5m_input_tokens": 0},
  "cache_read_input_tokens": 0,
  "input_tokens": 0,
  "output_tokens": 52,
  "service_tier": "standard",
  "iterations": [],
  "speed": "standard"
}
```

Stream events contained only text-oriented events:

```text
message_start
content_block_start(block_type=text)
content_block_delta(delta_type=text_delta)
content_block_stop(block_type=text)
message_delta
message_stop
```

Final content blocks:

```text
["text"]
```

No visible reasoning blocks were returned:

```text
thinking_blocks=[]
redacted_thinking absent
thinking_delta absent
reasoning_tokens=0 in Hermes result
```

## Conclusion

Hermes **does** forward high reasoning for Kie/Claude Sonnet 5 through the Anthropic Messages runtime path:

```json
"thinking": {"type":"adaptive","display":"summarized"},
"output_config": {"effort":"high"}
```

Kie accepts the request and returns a valid answer, but the response exposes only `text` content blocks. Treat Kie's advertised thinking support as **request accepted**, not as proof that visible thinking will be returned to Hermes.

## Reusable workflow

When validating whether a Hermes provider receives the real runtime payload:

1. Do not rely on a direct curl/urllib prompt; that only proves connectivity.
2. Instantiate `AIAgent` with the exact provider/model/api_mode/reasoning config.
3. Proxy the SDK method that will send the request (`messages.stream` for Anthropic Messages) and capture kwargs before forwarding.
4. Let `run_conversation()` execute normally so Hermes builds the true system prompt, tool schemas, memory/context, and messages.
5. Capture both request shape and response blocks/events.
6. Report only what the wire capture proves; do not infer visible thinking from a 200 response.
