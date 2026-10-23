# NVIDIA NIM — Free-Tier Provider Setup

**Endpoint**: `https://integrate.api.nvidia.com/v1`
**Auth**: Bearer token (`nvapi-...`)
**Free tier**: ~1000 inference calls/day, no credit card required
**Key generation**: https://build.nvidia.com → Avatar → API Keys → Generate (requires manual browser login — NVIDIA SSO uses OAuth + JS rendering, cannot be automated headlessly). Credentials stored in Bitwarden: `lucas.jouvencon@gmail.com` / `Lania-Kea`.

## Discovering Available Models

The `/v1/models` endpoint is **unauthenticated** — list models before committing:

```bash
# Step 1: fetch model list
curl -s https://integrate.api.nvidia.com/v1/models -o /tmp/nvidia_models.json
# Step 2: extract IDs
python3 -c "import json; [print(m['id']) for m in json.load(open('/tmp/nvidia_models.json')).get('data',[])]"
```

As of 2026-06, the free tier includes (AA = Artificial Analysis Intelligence Index, updated 2026-06-10):

| Model | ID | AA | Notes |
|-------|----|----|-------|
| Kimi K2.6 | `moonshotai/kimi-k2.6` | **53.9** | 1T MoE, frontier-level, best free model by AA |
| DeepSeek V4 Pro | `deepseek-ai/deepseek-v4-pro` | **52.0** | Flagship (reasoning max mode) |
| Nemotron Ultra 550B | `nvidia/nemotron-3-ultra-550b-a55b` | **47.7** | NVIDIA flagship, cold start > 90s |
| DeepSeek V4 Flash | `deepseek-ai/deepseek-v4-flash` | **46.5** | Fast variant |
| Qwen 3.5 397B | `qwen/qwen3.5-397b-a17b` | 45 | Largest free Qwen |
| Qwen 3.5 122B | `qwen/qwen3.5-122b-a10b` | 42 | Lighter variant |
| Qwen 3 Coder 480B | `qwen/qwen3-coder-480b-a35b-instruct` | N/A | Coding specialist |
| Mistral Large 3 675B | `mistralai/mistral-large-3-675b-instruct-2512` | 23 | Surprisingly low AA score |
| Mistral Medium 3.5 128B | `mistralai/mistral-medium-3.5-128b` | N/A | |
| Nemotron Super 49B | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | N/A | Smaller, fast |

**Frontier-tier (AA > 46):** Kimi K2.6, DeepSeek V4 Pro, Nemotron Ultra 550B, DeepSeek V4 Flash — competitive with paid frontier models at $0 cost.

**Model list changes** — re-run the fetch above if models return 404.

## Config Pattern

### `.env`
```
NVIDIA_API_KEY=nvapi-YOUR_KEY_HERE
```

### `config.yaml` — provider entry
```yaml
providers:
  nvidia:
    name: "NVIDIA NIM"
    api: https://integrate.api.nvidia.com/v1
    default_model: moonshotai/kimi-k2.6
    key_env: NVIDIA_API_KEY
    auth_style: bearer_token
    models:
      - moonshotai/kimi-k2.6
      - deepseek-ai/deepseek-v4-pro
      - deepseek-ai/deepseek-v4-flash
      - qwen/qwen3-coder-480b-a35b-instruct
      - qwen/qwen3.5-397b-a17b
      - qwen/qwen3.5-122b-a10b
      - mistralai/mistral-large-3-675b-instruct-2512
      - mistralai/mistral-medium-3.5-128b
      - nvidia/nemotron-3-ultra-550b-a55b
      - nvidia/llama-3.3-nemotron-super-49b-v1.5
```

### Fallback chain — cost optimization

Place `nvidia` as **first fallback** to exploit free tier before falling through to paid providers:

```yaml
fallback_providers:
  - provider: nvidia
    model: moonshotai/kimi-k2.6
  - provider: nvidia
    model: deepseek-ai/deepseek-v4-pro
  - provider: nvidia
    model: qwen/qwen3.5-397b-a17b
  - provider: nvidia
    model: nvidia/nemotron-3-ultra-550b-a55b
  - provider: openrouter
    model: moonshotai/kimi-k2.6
  # ... rest of existing fallbacks
```

**Rationale**: Free-tier models cost $0 — exhaust them before touching OpenRouter credits.

## Pitfalls

1. **OpenRouter `:free` suffix is unreliable.** Many models listed as free on OpenRouter don't actually route to free endpoints. Direct NVIDIA access is more reliable for free-tier inference.

2. **Model IDs are provider-specific.** `moonshotai/kimi-k2.6` on NVIDIA NIM is a different endpoint than `moonshotai/kimi-k2.6:free` on OpenRouter. Different rate limits, different availability.

3. **Free tier has daily limits.** 429 errors mean the daily quota is exhausted. Resets at midnight UTC.

4. **No streaming quirks.** NVIDIA NIM uses standard OpenAI-compatible streaming. No adapter patches needed (unlike Kie.ai or Bedrock).

5. **Auth style must be `bearer_token`.** The default `api_key` style (x-api-key header) will return 401.

6. **Cold start on large models (550B+).** Nemotron Ultra 550B and similarly large models may timeout on first request (> 90s) due to serverless cold start on the free tier. Subsequent requests are fast. If a model returns timeout on first call, retry — it's not a config error. Hermes fallback chain handles this automatically (timeout → next fallback entry). Verified: Kimi K2.6 and DeepSeek V4 Flash respond in < 3s; Nemotron Ultra 550B takes 90s+ on cold start.

## Quick Test

```bash
hermes chat -q "Say OK" -m moonshotai/kimi-k2.6 --provider nvidia -Q
```
