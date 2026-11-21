# Verifying Actual Provider Routing

## Problem
Config says `provider: xiaomi` but user insists they're on OpenRouter. Or config says direct Xiaomi but calls actually go through GitLawb gateway.

## Method
Check request dumps — they capture the actual HTTP request sent to the LLM API.

```bash
# Latest request dump
ls -lt ~/.hermes/sessions/request_dump_*.json | head -1

# Extract URL + model
python3 -c "
import json, glob, os
files = sorted(glob.glob(os.path.expanduser('~/.hermes/sessions/request_dump_*.json')))
with open(files[-1]) as f:
    data = json.load(f)
req = data.get('request', {})
body = json.loads(req.get('body', '{}'))
print('URL:', req.get('url'))
print('Model:', body.get('model'))
print('Auth:', req.get('headers', {}).get('Authorization', 'N/A')[:30] + '...')
"
```

## URL → Provider Mapping
| URL pattern | Actual provider |
|---|---|
| `api.openrouter.ai` | OpenRouter |
| `opengateway.gitlawb.com` | GitLawb proxy (wraps Xiaomi MiMo) |
| `token-plan-ams.xiaomimimo.com` | Direct Xiaomi MiMo plan |
| `api.anthropic.com` | Anthropic direct |
| `generativelanguage.googleapis.com` | Google Gemini direct |

## Why Config ≠ Reality
1. **Provider declaration overrides base_url**: If `providers.xiaomi.api` points to GitLawb, all calls route there regardless of `model.base_url`
2. **Fallback chain**: Primary fails → silently falls back to OpenRouter entry in `fallback_providers`
3. **Credential pool rotation**: Multiple keys in the same provider pool may route differently
4. **Mid-session override**: `/model` or `/provider` slash commands change routing without updating config.yaml
