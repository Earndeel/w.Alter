# Kie.ai Pricing Research Notes

Session: May 10, 2026. Method: live API probes with authenticated requests.

## Credit-to-USD conversion

1 Kie.ai credit ≈ **$0.005 USD**

Derived from two controlled API calls to `claude-opus-4-6`:

| Probe | Input tokens | Output tokens | Credits consumed |
|-------|-------------|---------------|------------------|
| Short (max_tokens=1) | 45 | 130 | 0.20 |
| Long (max_tokens=4000) | 240 | 10,460 | 15.03 |

Solving the linear system:
- Input cost: ~$0.002–0.0025 / 1K tokens (≈ $2.00–2.50 / M)
- Output cost: ~$0.007–0.0075 / 1K tokens (≈ $7.00–7.50 / M)

## OpenRouter comparison (Claude Opus 4.6)

| Metric | OpenRouter | Kie.ai | Ratio |
|--------|-----------|--------|-------|
| Input | $5.00 / M | ~$2.25 / M | **2.2× cheaper** |
| Output | $25.00 / M | ~$7.25 / M | **3.4× cheaper** |
| 1M in + 1M out | $30.00 | ~$9.50 | **3.2× cheaper** |

Source: OpenRouter API `GET /api/v1/models` on May 10, 2026:
```
anthropic/claude-opus-4.6: input=0.000005, output=0.000025
```

## Account balance endpoint

```bash
curl -s -H "Authorization: Bearer $(vault get kie/api_key)" \
  https://api.kie.ai/api/v1/chat/credit
```

Returns:
```json
{"code":200,"msg":"success","data":879.7}
```

`data` is a float representing remaining credits.

## Key API endpoints discovered

| Service | Endpoint |
|---------|----------|
| Claude messages | `POST https://api.kie.ai/claude/v1/messages` |
| GPT (OpenAI-compatible) | `POST https://api.kie.ai/chat/v1/messages` |
| **Gemini 3.1 Pro** | `POST https://api.kie.ai/gemini-3.1-pro/v1/chat/completions` |
| **Gemini 3.5 Flash** | `POST https://api.kie.ai/gemini-3-5-flash-openai/v1/chat/completions` |
| **Gemini 3.5 Flash (native)** | `POST https://api.kie.ai/gemini/v1/models/gemini-3-5-flash:generateContent` |
| Credits balance | `GET https://api.kie.ai/api/v1/chat/credit` |
| Task creation | `POST https://api.kie.ai/api/v1/jobs/createTask` |
| Task detail (legacy) | `GET https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId=...` |
| Task detail (market) | `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...` |
| Download URL | `POST https://api.kie.ai/api/v1/common/download-url` |

## Gemini endpoint discovery (June 2, 2026)

Each Gemini model on Kie.ai has its OWN endpoint with the model name in the URL path. The `/openai/v1/chat/completions` endpoint does NOT support Gemini models. The `/gemini/v1/chat/completions` endpoint also does NOT work.

**Working pattern:** `POST https://api.kie.ai/{model-name}/v1/chat/completions` with standard OpenAI chat completions body.

| Model | URL model-name | Body model field | Format |
|-------|---------------|-----------------|--------|
| Gemini 3.5 Flash | `gemini-3-5-flash-openai` | `gemini-3-5-flash` | OpenAI compat |
| Gemini 3.1 Pro | `gemini-3.1-pro` | `gemini-3.1-pro` | OpenAI compat |
| Gemini 3 Flash | `gemini-3-flash` | `gemini-3-flash` | OpenAI compat |
| Gemini 3 Pro | `gemini-3-pro` | `gemini-3-pro` | OpenAI compat |
| Gemini 2.5 Flash | `gemini-2.5-flash` | `gemini-2.5-flash` | OpenAI compat |
| Gemini 2.5 Pro | `gemini-2.5-pro` | `gemini-2.5-pro` | OpenAI compat |

**Pricing:** 0.01 credits/call (~$0.00005) for short requests. Balance check: 5976.09 credits (June 2026).

## Browser automation pitfall

Google OAuth login on kie.ai is aggressively blocked for headless/Playwright browsers even with anti-detection flags and Xvfb. The reliable automation path is API-key-only via `vault get kie/api_key`. Do not waste time trying to automate the dashboard login.

## Documentation source

Official docs: https://docs.kie.ai (Apidog-generated)
- Model-specific pages: `/market/<provider>/<model>/`
- Common API: `/common-api/quickstart`
- File upload: `/file-upload-api/quickstart`
