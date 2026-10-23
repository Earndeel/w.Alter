# Higgsfield → FAL Fallback Pattern

## When to trigger

Higgsfield MCP tools (`mcp_higgsfield_*`) are served through an external MCP server. When the server is unreachable,
**every call returns a digest-only result** — no actual content, no error message, just `[TOOL RESULT DIGEST]`.

**Signal**: 3+ consecutive calls to any `mcp_higgsfield_*` tool returning digest-only = server down.
Do NOT keep retrying immediately — each attempt burns a turn with no progress.

## Retry protocol

1. After the first digest-only result, wait **30 seconds** (`sleep 30`) and retry once.
2. If still digest-only, **declare Higgsfield unavailable** and move to fallback.
3. Do NOT attempt more than 2 total Higgsfield calls in a session when it's down.

## FAL direct API fallback

When Higgsfield is down, use the FAL REST API directly (bypasses MCP layer):

```bash
FAL_KEY="<from-vault>"

curl -s -X POST "https://fal.run/fal-ai/kling-video/v1.6/standard/text-to-video" \
  -H "Authorization: Key $FAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "<PROMPT>",
    "duration": "5",
    "aspect_ratio": "16:9"
  }'
```

### Kling model versions
- `fal-ai/kling-video/v1.6/standard/text-to-video` — latest stable
- `fal-ai/kling-video/v1.5/pro/text-to-video` — pro tier
- `fal-ai/kling-video/v1/standard/text-to-video` — legacy

### Parameters
| Param | Type | Default | Notes |
|-------|------|---------|-------|
| prompt | string | required | Max ~2500 chars |
| duration | string | "5" | "5" or "10" (seconds) |
| aspect_ratio | string | "16:9" | "16:9", "9:16", "1:1" |
| cfg_scale | float | 0.5 | Prompt adherence (0-1) |
| negative_prompt | string | "" | What to avoid |

### FAL credit exhaustion
If FAL returns `"Exhausted balance"`, credits are depleted. Options:
- Recharge via fal.ai dashboard
- Try Higgsfield again later (cron job)
- Use an alternative provider (Runway, Pika, etc.) if keys are available
