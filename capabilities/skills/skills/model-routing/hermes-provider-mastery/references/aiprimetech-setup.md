# AI PrimeTech Provider Setup

Third-party endpoint via GamsGo.com. Serves multiple model families under one API key.

## Endpoint: Claude Models via Kiro (verified 2026-06-26)

The endpoint `https://aiprimetech.io` serves **Claude models** via OpenAI-compatible API, routed through Amazon Kiro credentials.

```bash
# Test: list models (24 Claude models returned)
curl -s "https://aiprimetech.io/v1/models" -H "Authorization: Bearer <KEY>"

# Test: chat completion
curl -s -X POST "https://aiprimetech.io/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <KEY>" \
  -d '{"model":"claude-opus-4-8","max_tokens":50,"messages":[{"role":"user","content":"say hi"}]}'
```

### Confirmed working models (2026-06-26)

| Model | Status | Notes |
|---|---|---|
| `claude-haiku-4-5` | ✅ Works | Consistent |
| `claude-sonnet-4-6` | ✅ Works | Consistent |
| `claude-opus-4-6` | ✅ Works | Consistent |
| `claude-opus-4-8` | ✅ Works | Intermittent (see Pitfalls) |
| `claude-opus-4-8-thinking` | Listed | Not tested |
| `claude-opus-4-7` / `4-7-thinking` | Listed | Not tested |
| `MiniMax-M3` | Listed | Previously primary, now secondary |

## Provider Config (chat_completions mode)

```yaml
providers:
  aiprimetech:
    api: https://aiprimetech.io
    api_mode: chat_completions      # NOT anthropic_messages
    default_model: claude-opus-4-8
    key_env: AIPRIMETECH_API_KEY
    models:
      - claude-opus-4-8
      - claude-opus-4-8-thinking
      - claude-opus-4-7
      - claude-opus-4-6
      - claude-opus-4-5-20251101
      - claude-opus-4-1-20250805
      - claude-opus-4-20250514
      - claude-sonnet-4-6
      - claude-sonnet-4-5-20250929
      - claude-haiku-4-5
      - MiniMax-M3
    name: AI PrimeTech
    request_timeout_seconds: 120
```

### Critical: api_mode is `chat_completions`

The endpoint uses OpenAI-compatible format (`/v1/chat/completions`), NOT Anthropic Messages API (`/v1/messages`). Using `anthropic_messages` causes authentication or proxy errors.

## .env Entries

```bash
AIPRIMETECH_API_KEY=sk-...
```

**Do NOT set `ANTHROPIC_BASE_URL=https://aiprimetech.io`** — this contaminates the real Anthropic provider.

## Kiro Backend Behavior

The proxy routes through Amazon Kiro credentials. This causes:

1. **Intermittent 400 errors** — "Model is not supported by the currently available Kiro credentials" with Chinese error text. The same model (claude-opus-4-8) can succeed on one call and fail on the next.
2. **Timeout sensitivity** — Default 20s timeout sometimes insufficient; 60s recommended.
3. **Credential rotation** — Kiro credentials appear to rotate server-side, causing transient unavailability.

**Test pattern for reliability check:**
```python
import requests, time
for i in range(3):
    resp = requests.post("https://aiprimetech.io/v1/chat/completions", ...)
    print(f"Attempt {i+1}: {resp.status_code}")
    time.sleep(2)
```

## Historical Timeline

| Date | State | Models |
|---|---|---|
| 2026-06-06 | Claude via Kiro | claude-opus-4-6, 4-7, 4-8 |
| 2026-06-08 | 403/401 errors | Credentials unstable |
| 2026-06-15 | MiniMax-M3 only | Claude removed |
| 2026-06-26 | Claude restored | 24 Claude models + MiniMax-M3 |

## Pricing

- ~88% discount vs direct pricing (via GamsGo)
- No SLA, no official support

## Pitfalls

- **`api_mode` MUST be `chat_completions`** — not `anthropic_messages`
- **Sed bulk-replace danger** — Using `sed` to change `api_mode` for one provider can accidentally change ALL providers in config.yaml. Always use targeted edits (Python string replace with unique context) instead of global sed patterns.
- **`/v1/models` endpoint requires `Authorization: Bearer` header** (not `x-api-key`)
- **Kiro credential errors are intermittent** — retry 3x with 2s delay before concluding the key is invalid
- **`ANTHROPIC_BASE_URL` env var contamination** — Setting this to aiprimetech.io breaks the real Anthropic provider
- **Config change requires `hermes gateway restart`** to take effect
- **Not suitable for production coding** — Use for testing/evaluation only; prefer Bedrock or direct Anthropic for serious work
