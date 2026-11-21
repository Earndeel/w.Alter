# Kie.ai Cloudflare WAF Debugging — Full Reproduction

## How the root cause was isolated (2026-06-03)

### Step 1: Confirm the error in Hermes logs
```bash
tail -100 ~/.hermes/logs/errors.log | grep -i "blocked\|403\|PermissionDenied"
```
Output: `PermissionDeniedError ... HTTP 403: Your request was blocked.`

### Step 2: Test API directly with curl (WORKS)
```bash
curl -s "https://api.kie.ai/gemini-3-5-flash-openai/v1/chat/completions" \
  -H "Authorization: Bearer *** \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3-5-flash","messages":[{"role":"user","content":"say OK"}],"max_tokens":5}'
```
Returns HTTP 200 with valid response.

### Step 3: Test with requests library (WORKS)
```python
import requests
resp = requests.post(url, headers={...}, json=payload)
# HTTP 200
```

### Step 4: Test with httpx direct (WORKS)
```python
import httpx
resp = httpx.post(url, headers={...}, json=payload)
# HTTP 200
```

### Step 5: Test with OpenAI Python client (FAILS)
```python
from openai import OpenAI
client = OpenAI(api_key=key, base_url="https://api.kie.ai/gemini-3-5-flash-openai/v1")
resp = client.chat.completions.create(model="gemini-3-5-flash", messages=[...])
# Error: Your request was blocked.
```

### Step 6: Capture headers sent by OpenAI client
Intercept `httpx.Client.send` to log outgoing headers:
```
user-agent: OpenAI/Python 2.24.0
x-stainless-lang: python
x-stainless-package-version: 2.24.0
x-stainless-os: Linux
x-stainless-arch: arm64
x-stainless-runtime: CPython
x-stainless-runtime-version: 3.11.15
```

### Step 7: Confirm User-Agent is the trigger
Test httpx with the same User-Agent as OpenAI client → HTTP 403 (BLOCKED)
Test httpx with a different User-Agent → HTTP 200 (OK)

### Conclusion
Cloudflare WAF on api.kie.ai blocks `User-Agent: OpenAI/Python *`. NOT Gemini's safety filter.

## Why agent_init.py fix was insufficient

The first fix was in `agent/agent_init.py` (~line 735). This only covers **initial** client creation.

When the user switches model via `/model` in TUI:
1. `model_switch.switch_model()` resolves credentials
2. `agent_runtime_helpers.switch_model()` builds `_client_kwargs` directly (line ~1471): `{"api_key": ..., "base_url": ...}` — NO `default_headers`
3. Calls `create_openai_client()` → `OpenAI(**client_kwargs)` — `agent_init.py` check NEVER reached

Correct fix: `create_openai_client()` in `agent/agent_runtime_helpers.py` (~line 1255).

## Error signature table

| Source | Error | HTTP | Meaning |
|--------|-------|------|---------|
| Cloudflare WAF | "Your request was blocked" | 403 | Bot detection on User-Agent |
| Gemini safety | safety messages | 200 + `SAFETY` | Content filtering |
| Kie.ai rate limit | "Rate limit exceeded" | 429 | Too many requests |
| Kie.ai auth | "Unauthorized" | 401 | Bad API key |
