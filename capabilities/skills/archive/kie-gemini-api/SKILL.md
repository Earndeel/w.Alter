---
name: kie-gemini-api
description: Kie.ai Gemini models — correct endpoints, model IDs, request/response formats. Google native generateContent API, NOT OpenAI-compatible.
version: 1.0.0
author: W.Albert
license: MIT
metadata:
  hermes:
    tags: [kie, gemini, llm, api, google]
---

# Kie.ai Gemini API

Gemini models on Kie.ai use **Google's native `generateContent` API**, NOT OpenAI-compatible endpoints. Tested 2026-06-02.

## Reference Files

- `references/gemini-test-results.md` — Full empirical test matrix (all models × all endpoints, HTTP status codes, body sizes, error messages)

## Quick Reference — Confirmed Working

### gemini-3-5-flash ✅ (Recommended)

```bash
curl -s -X POST "https://api.kie.ai/gemini/v1/models/gemini-3-5-flash:generateContent" \
  -H "Authorization: Bearer *** get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{"contents": [{"parts": [{"text": "Your prompt"}]}]}'
```

- Cost: 0.01 credits/call (~$0.00005)
- Non-streaming JSON response
- Includes `usageMetadata` with `thinkingTokenCount` (reasoning tokens)

### gemini-3-flash-v1betamodels ✅ (Streaming only)

```bash
curl -s -X POST "https://api.kie.ai/gemini/v1/models/gemini-3-flash-v1betamodels:streamGenerateContent" \
  -H "Authorization: Bearer *** get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{"contents": [{"parts": [{"text": "Your prompt"}]}]}'
```

- SSE streaming: `data: {...}` lines, ends with `data: [DONE]`
- Non-streaming `:generateContent` returns empty body for this model

## Endpoint Pattern

```
POST https://api.kie.ai/gemini/v1/models/{model_id}:generateContent
POST https://api.kie.ai/gemini/v1/models/{model_id}:streamGenerateContent
```

Each model has its own endpoint path. No shared chat/completions for Gemini.

## Non-Working Models (as of 2026-06-02)

| Model ID | Endpoint | Result |
|----------|----------|--------|
| gemini-3.1-pro | `:generateContent` | HTTP 200, content-length: 0 |
| gemini-3-1-pro | `:generateContent` | 422 "page does not exist" |
| gemini-3-flash | `:generateContent` | HTTP 200, content-length: 0 |
| gemini-3-pro | `:generateContent` | HTTP 200, content-length: 0 |
| gemini-2.5-flash | `:generateContent` | HTTP 200, content-length: 0 |
| gemini-2.5-pro | `:generateContent` | HTTP 200, content-length: 0 |
| ALL Gemini | `/openai/v1/chat/completions` | 422 "model not supported" |
| ALL Gemini | `/gemini/v1/chat/completions` | 422 "model not supported" |

**Empty body pattern**: HTTP 200 with `content-length: 0` = endpoint exists but model not deployed. Different from 422 (endpoint missing).

## Request Format (Google Native)

```json
{"contents": [{"parts": [{"text": "Prompt"}]}]}
```

With config:
```json
{"contents": [{"parts": [{"text": "Prompt"}]}], "generationConfig": {"maxOutputTokens": 10}}
```

With system instruction:
```json
{"system_instruction": {"parts": [{"text": "System"}]}, "contents": [{"role": "user", "parts": [{"text": "Prompt"}]}]}
```

## Response Format

Non-streaming:
```json
{
  "candidates": [{"finishReason": "STOP", "index": 0, "content": {"role": "model", "parts": [{"text": "OK"}]}}],
  "usageMetadata": {"thinkingTokenCount": 158, "candidatesTokenCount": 1, "totalTokenCount": 242, "promptTokenCount": 83},
  "credits_consumed": 0.01
}
```

Streaming (SSE):
```
data: {"candidates": [{"content": {"role": "model", "parts": [{"text": "OK"}]}}]}

data: {"usageMetadata": {...}, "credits_consumed": 0.01}

data: [DONE]
```

## Endpoint Discovery

Docs HTML at `https://docs.kie.ai` bundles all model paths. Grep them:

```bash
curl -s "https://docs.kie.ai" | grep -oP '(?:gemini|openai|chat|claude)/[^"\\]+' | sort -u
```

## Pitfalls

- **Do NOT use OpenAI-compatible endpoints for Gemini.** `/openai/v1/chat/completions`, `/gemini/v1/chat/completions`, `/chat/v1/messages` all return 422.
- **Model ID naming is inconsistent.** `gemini-3-5-flash` (hyphens) works. `gemini-3.1-pro` (dots) hits endpoint but returns empty. `gemini-3-1-pro` (hyphens) returns 422. Always test empirically.
- **Empty body ≠ error.** HTTP 200 with content-length 0 = model not deployed. Check response size, not just status.
- **Streaming vs non-streaming varies.** Some models only work with `:streamGenerateContent`. If empty body on `:generateContent`, try streaming.
- **`write_file` tool expands `$key` variables** when content contains strings like `"Bearer " + key`. Use `cat` heredoc in terminal to write Python scripts that construct auth headers from vault keys.

## Related Skills

- `kie-video-generation` — parent skill covering video/image/chat models on Kie.ai
- `vault-lookup` — retrieve `kie/api_key`
