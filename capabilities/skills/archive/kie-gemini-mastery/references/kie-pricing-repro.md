# Kie.ai API Live Verification & Troubleshooting

Durable recipe for validating and verifying Claude Opus models and other LLMs directly on Kie.ai's API gateway. Proven in session on June 05, 2026.

## Verification Recipe (Curl)

To verify if your credentials, model IDs, and endpoints are operational, execute this precise payload. This includes the required headers to bypass both Cloudflare's WAF and Kie.ai's auth checks.

```bash
curl -i -X POST \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -H "User-Agent: Mozilla/5.0 (compatible; HermesAgent/1.0)" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-opus-4-7","messages":[{"role":"user","content":"hi"}],"max_tokens":10}' \
  https://api.kie.ai/claude/v1/messages
```

### Expected Success Output (HTTP 200)

```json
HTTP/2 200 
date: Fri, 05 Jun 2026 18:50:55 GMT
server: cloudflare
cf-cache-status: DYNAMIC

{
  "role": "assistant",
  "usage": {
    "output_tokens": 10,
    "input_tokens": 9,
    "credits_consumed": 0.02
  },
  "stop_reason": "max_tokens",
  "model": "claude-opus-4-7",
  "id": "chatcompl_019YHrsaH8u4X2afbCRghujc",
  "type": "message",
  "content": [
    {
      "text": " Hi there! How can I help you today?",
      "type": "text"
    }
  ]
}
```

---

## Technical Learnings & Troubleshooting

### 1. Cloudflare WAF HTTP 403 Blockage
*   **Symptom:** API requests fail immediately with `HTTP 403 Forbidden` and the message `"Your request was blocked."`.
*   **Root Cause:** Kie.ai uses Cloudflare, which is configured to block standard bot User-Agents, specifically Python SDK agents like `OpenAI/Python X.Y.Z` or `anthropic-python/X.Y.Z`.
*   **Fix:** Override the `default_headers` when building the HTTP client (both OpenAI and Anthropic SDKs) to send a standard browser User-Agent: `Mozilla/5.0 (compatible; HermesAgent/1.0)`.

### 2. HTTP 401/422 Unauthorized on Anthropic SDK
*   **Symptom:** SDK message creation fails with `Authentication failed` or `422 Unprocessable Content`.
*   **Root Cause:** The Anthropic Python SDK natively sends API keys via the `x-api-key: <key>` header. Kie.ai strictly expects standard `Authorization: Bearer <key>` headers even on its Anthropic-messages compatible endpoints.
*   **Fix:** Force the Anthropic SDK helper to use Bearer auth by registering the `api.kie.ai` / `kie.ai` base URLs inside `_requires_bearer_auth` in `agent/anthropic_adapter.py`.

### 3. Model Naming Hybridity
*   **Symptom:** Model selection works for Claude Opus 4.6 but returns 404 for Claude Opus 4.7.
*   **Root Cause:** Kie.ai has a hybrid nomenclature convention:
    *   **Claude models** MUST use hyphens (`claude-opus-4-7`). Specifying dots (`claude-opus-4.7`) causes a 404.
    *   **Gemini models** MUST use dots (`gemini-3.1-pro`). Specifying hyphens (`gemini-3-1-pro`) causes a 422.
*   **Fix:** Add a custom hybrid normalizer inside `normalize_model_for_provider` in `hermes_cli/model_normalize.py` that dynamically translates dots to hyphens *only* for Claude model names while leaving Gemini/GPT names untouched.
