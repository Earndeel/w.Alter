# Tool-Use Formats — Kie.ai Endpoints

## GPT models (Responses API)

Endpoint: `POST https://api.kie.ai/codex/v1/responses`

### Full agentic loop example

```python
import json, requests
UA = "Mozilla/5.0 ... Chrome/131 Safari/537.36"
h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": UA}

tools = [{"type": "function", "name": "search", "description": "...",
          "parameters": {"type": "object", "properties": {...}}}]

# Step 1: Model decides to call tool
r = requests.post("https://api.kie.ai/codex/v1/responses", headers=h, json={
    "model": "gpt-5-6-luna",
    "input": [{"role": "user", "content": "Search for X"}],
    "tools": tools, "tool_choice": "auto",
    "max_output_tokens": 500,
}, stream=True)

# Parse streaming response to find function_call
call_id = None  # e.g. "call_8QQrslXcbNbb9FokEljysK7T"
fc_id = f"fc_{call_id[5:]}"  # MUST convert call_ → fc_ prefix!

# Step 2: Send tool result
result = json.dumps({"found": True, "data": [...]})
r2 = requests.post("https://api.kie.ai/codex/v1/responses", headers=h, json={
    "model": "gpt-5-6-luna",
    "input": [
        {"role": "user", "content": "Search for X"},
        {"type": "function_call", "call_id": fc_id, "name": "search", "arguments": '{"query":"X"}'},
        {"type": "function_call_output", "call_id": fc_id, "output": result},
    ],
    "max_output_tokens": 500,
}, stream=True)
```

### Streaming event types

| Event type | Meaning |
|---|---|
| `response.output_item.added` | New output item (reasoning, function_call, message) |
| `response.function_call_arguments.delta` | Streaming function call arguments |
| `response.output_item.done` | Item complete — function_call has `call_id`, `name`, `arguments` |
| `response.output_text.delta` | Streaming text delta |
| `response.completed` | Full response done — has `usage` |

## Claude models (Anthropic Messages API)

Endpoint: `POST https://api.kie.ai/claude/v1/messages`

```python
# Step 1: Model decides to call tool
r = requests.post("https://api.kie.ai/claude/v1/messages", headers=h, json={
    "model": "claude-opus-5",
    "max_tokens": 300,
    "messages": [{"role": "user", "content": "What's the weather?"}],
    "tools": [{"name": "get_weather", "input_schema": {...}}],
})

# Step 2: Find tool_use block
for block in r.json()["content"]:
    if block["type"] == "tool_use":
        tool_use = block  # has id, name, input

# Step 3: Send tool result
r2 = requests.post("https://api.kie.ai/claude/v1/messages", headers=h, json={
    "model": "claude-opus-5",
    "max_tokens": 300,
    "messages": [
        {"role": "user", "content": "What's the weather?"},
        {"role": "assistant", "content": [tool_use]},
        {"role": "user", "content": [{
            "type": "tool_result",
            "tool_use_id": tool_use["id"],
            "content": json.dumps({"temp": 22, "condition": "sunny"})
        }]},
    ],
})
```

### Anthropic tool-use test results (2026-07-29)

- Claude Opus 5 via Kie.ai: Step 1 = 3.6s, Step 2 = 5.2s, Total = 8.7s
- Coût estimé: ~$0.0005 pour cette tâche (212 in + 252 out tokens)
