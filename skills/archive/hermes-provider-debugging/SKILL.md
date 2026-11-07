---
name: hermes-provider-debugging
description: "Debug Hermes provider configuration issues — auxiliary service 401 errors, key resolution, provider declarations, fallback chains."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [hermes, provider, debugging, api-key, auxiliary]
    related_skills: [hermes-agent, hermes-gateway-systemd-debug]
---

# Hermes Provider Debugging

Debug provider configuration issues when auxiliary services fail but the main model works.

## When to Use

- `Auxiliary title generation failed: HTTP 401: Invalid API Key`
- Auxiliary services (vision, compression, etc.) return 401
- Main model works but delegates/subagents fail
- Provider resolution errors in logs

## Decision Tree

```
Auxiliary service 401?
├─ Check agent.log for actual provider + base_url used
│   └─ grep "API call failed.*401" ~/.hermes/logs/agent.log
├─ Is the main model also failing?
│   ├─ Yes → API key is invalid/expired
│   │   └─ Check vault: `vault search <provider>`
│   │   └─ Vault is source of truth for API keys
│   └─ No → Main model has fallback, auxiliary doesn't
│       └─ Check fallback_providers in config
│       └─ Explicitly configure auxiliary provider
└─ Is the provider declared in `providers` section?
    ├─ No → Add provider declaration with key_env
    └─ Yes → Check key_env maps to correct env var
```

## Key Resolution Chain

Hermes resolves API keys in this order:
1. `api_key` field in the auxiliary/service config
2. Provider's `key_env` → environment variable
3. Fallback providers (if configured)

**Critical**: If `provider: auto` is set but no provider is declared in the `providers` section, the key resolution fails silently and falls back to the main model's provider (which may not have a key configured for auxiliary use).

## Common Fixes

### 1. Provider not declared

The main model can use `provider: xiaomi` with `base_url` directly, but auxiliary services need the provider declared in `providers` section for key resolution:

```yaml
# config.yaml
providers:
  xiaomi:
    name: Xiaomi MiMo
    api: https://token-plan-ams.xiaomimimo.com/v1
    default_model: mimo-v2.5
    key_env: XIAOMI_API_KEY
    models: ["mimo-v2.5"]
```

### 2. Auxiliary service needs explicit provider

When `provider: auto` fails, explicitly set the auxiliary service:

```yaml
auxiliary:
  title_generation:
    provider: openrouter  # or specific provider
    model: xiaomi/mimo-v2.5
    base_url: ""
```

### 3. API key expired

The vault is source of truth. Always check vault first:

```bash
vault search <provider>
vault get <provider>/api_key
```

## Log Analysis

```bash
# Find all 401 errors
grep "HTTP 401" ~/.hermes/logs/agent.log | tail -20

# Check which provider/model was used
grep "API call.*provider=" ~/.hermes/logs/agent.log | tail -10

# Check fallback behavior
grep "fallback" ~/.hermes/logs/agent.log | tail -10
```

## Verifying ACTUAL Provider (Not Just Config)

`hermes config` and `hermes status` show what's **configured**, not what's **actually hitting the API**. The real routing may differ due to fallback chains, provider proxy gateways, or mid-session overrides.

**Check request dumps** — the ground truth:
```bash
python3 -c "
import json, glob, os
files = sorted(glob.glob(os.path.expanduser('~/.hermes/sessions/request_dump_*.json')))
if files:
    with open(files[-1]) as f:
        data = json.load(f)
    req = data.get('request', {})
    body = json.loads(req.get('body', '{}'))
    print('url:', req.get('url', 'N/A'))
    print('model:', body.get('model', 'N/A'))
"
```

The URL reveals the true provider:
- `api.openrouter.ai` → OpenRouter
- `opengateway.gitlawb.com` → GitLawb proxy (MiMo)
- `token-plan-ams.xiaomimimo.com` → direct Xiaomi
- `api.anthropic.com` → Anthropic direct

**Common mismatch**: Config says `provider: xiaomi` with `base_url: https://token-plan-ams.xiaomimimo.com/v1` but actual calls go to `opengateway.gitlawb.com/v1/xiaomi-mimo` because the provider definition in `providers:` section overrides the base_url.

## Pitfalls

1. **Main model works via fallback**: The main model may silently fall back to OpenRouter when the primary provider fails. Check logs for `provider=openrouter` to confirm.

2. **Auxiliary services have different fallback chains**: `title_generation`, `vision`, `compression` etc. each have their own provider config. They don't inherit the main model's fallback.

3. **Vault vs .env mismatch**: The `.env` file may have an expired key while the vault has the correct one. Always use `vault get` to verify.

4. **Provider declaration required**: Even if the main model works with `provider: xiaomi` + `base_url`, the provider must be declared in `providers` section for auxiliary services to resolve the key via `key_env`.
