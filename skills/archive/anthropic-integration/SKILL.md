---
name: anthropic-integration
description: Anthropic Claude API — messages, streaming, tool use, vision, and SDK patterns (Python/JS).
category: mlops
---

# Anthropic (Claude) API Integration

## When to Use
- Calling Claude API for text generation, analysis, or tool use
- Implementing streaming responses or vision (image input)
- Setting up or troubleshooting the Anthropic Python/JS SDK
- Comparing Claude models (Haiku, Sonnet, Opus) for cost/performance

## API Basics

### Messages endpoint
```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Python SDK
```python
import anthropic
client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var

message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Explain monads"}]
)
print(message.content[0].text)
```

### Streaming
```python
with client.messages.stream(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Write a poem"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### Vision (image input)
```python
message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64_image}},
            {"type": "text", "text": "Describe this image"}
        ]
    }]
)
```

### Tool use
```python
tools = [{
    "name": "get_weather",
    "description": "Get weather for a city",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"]
    }
}]
message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "Weather in Paris?"}]
)
```

## Model Selection
| Model | Use case | Speed | Cost |
|-------|----------|-------|------|
| Haiku | Simple tasks, classification, extraction | Fast | Low |
| Sonnet | General purpose, coding, analysis | Medium | Medium |
| Opus | Complex reasoning, creative writing | Slow | High |

## Pitfalls
- `anthropic-version` header is required — missing it returns 400
- Max tokens is required (unlike OpenAI where it defaults)
- System prompt goes in the `system` parameter, not in messages
- Rate limits are per-model — check `anthropic.com/docs/rate-limits`
- Image size limit: 20MB, base64 increases size ~33%
- Tool use requires iterating the conversation loop until `stop_reason` is `"end_turn"`
- `ANTHROPIC_API_KEY` env var is the default — or pass `api_key=` to constructor
