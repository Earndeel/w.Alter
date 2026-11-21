# Kie.ai Gemini — Empirical Test Results

Date: 2026-06-02. Method: live API probes with authenticated requests via `vault get kie/api_key`.

## Test Matrix

### generateContent (non-streaming)

| Model ID | HTTP Status | Body Size | Result |
|----------|-------------|-----------|--------|
| gemini-3-5-flash | 200 | 238 bytes | ✅ `{"candidates":[...],"usageMetadata":{...},"credits_consumed":0.01}` |
| gemini-3.1-pro | 200 | 0 bytes | ❌ Empty body |
| gemini-3-1-pro | 422 | 155 bytes | ❌ "page does not exist" |
| gemini-3-flash | 200 | 0 bytes | ❌ Empty body |
| gemini-3-pro | 200 | 0 bytes | ❌ Empty body |
| gemini-2.5-flash | 200 | 0 bytes | ❌ Empty body |
| gemini-2-5-flash | 422 | — | ❌ "page does not exist" |
| gemini-2.5-pro | 200 | 0 bytes | ❌ Empty body |
| gemini-2-5-pro | 422 | — | ❌ "page does not exist" |
| gemini-3.1-pro-preview | 422 | — | ❌ "page does not exist" |
| gemini-3-5-flash-openai | 200 | 0 bytes | ❌ Empty body |

### streamGenerateContent (SSE)

| Model ID | HTTP Status | Body Size | Result |
|----------|-------------|-----------|--------|
| gemini-3-5-flash | 200 | 243 bytes | ✅ SSE with candidates + usage + [DONE] |
| gemini-3-flash-v1betamodels | 200 | 243 bytes | ✅ SSE with candidates + usage + [DONE] |
| gemini-3.1-pro | 200 | 0 bytes | ❌ Empty body |

### OpenAI-compatible endpoints (all return "not supported")

| Endpoint | Models Tested | Result |
|----------|---------------|--------|
| `/openai/v1/chat/completions` | gemini-3.1-pro, gemini-3-1-pro, gemini-3-flash, gemini-3.5-flash, gemini-3-5-flash, gemini-2.5-flash, gemini-2-5-flash, gemini-2.5-pro, gemini-2-5-pro | All 422 "model not supported" |
| `/gemini/v1/chat/completions` | Same set | All 422 "model not supported" |
| `/chat/v1/messages` | — | 404 (endpoint does not exist) |
| `/chat/v1/completions` | — | 404 |

## Endpoint Paths Found in Docs HTML

Extracted from `curl -s "https://docs.kie.ai" | grep -oP`:

**Gemini generateContent paths:**
- `gemini/v1/models/gemini-3-5-flash:streamGenerateContent`
- `gemini/v1/models/gemini-3-flash-v1betamodels:streamGenerateContent`

**Gemini market doc paths (not API endpoints):**
- `/market/gemini/gemini-2-5-flash`
- `/market/gemini/gemini-2-5-pro`
- `/market/gemini/gemini-3-1-pro`
- `/market/gemini/gemini-3-5-flash`
- `/market/gemini/gemini-3-5-flash-openai`
- `/market/gemini/gemini-3-flash`
- `/market/gemini/gemini-3-flash-v1beta`
- `/market/gemini/gemini-3-pro`

**Other chat/LLM endpoint patterns:**
- `openai/v1/chat/completions`
- `claude/v1/messages`

## Cost Observations

- gemini-3-5-flash: 0.01 credits per call (short prompt)
- gemini-3-flash-v1betamodels: 0.01 credits per call (short prompt)
- 1 credit ≈ $0.005 USD → 0.01 credits ≈ $0.00005 per call
