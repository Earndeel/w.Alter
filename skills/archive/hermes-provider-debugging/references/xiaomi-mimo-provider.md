# Xiaomi MiMo Provider Configuration

## Platform Architecture

| Domain | Purpose | Auth Method |
|--------|---------|-------------|
| `platform.xiaomimimo.com` | Web dashboard (React SPA) | Cookies (session login) |
| `token-plan-ams.xiaomimimo.com` | API endpoint | Bearer token (API key) |
| `mimo.xiaomi.com` | Marketing site | N/A |

## Provider Declaration (Required)

```yaml
providers:
  xiaomi:
    name: Xiaomi MiMo
    api: https://token-plan-ams.xiaomimimo.com/v1
    default_model: mimo-v2.5
    key_env: XIAOMI_API_KEY
    models: ["mimo-v2.5"]
```

## Key Resolution

- **Vault**: `vault get xiaomi/api_key` (source of truth)
- **Platform**: Dashboard → Console → API Keys (requires web login)
- **.env**: May be expired/out of sync with vault

## Cookie vs API Key

- Cookies from Mac Brave are for the web dashboard only
- `api-platform_serviceToken` does NOT work as API Bearer token
- API requires a separate API key (obtained from dashboard)

## Tested: 2026-06-02

- Vault key `tp-ekl...` works (HTTP 200)
- `.env` key `tp-sx5j...` was expired (HTTP 401)
- Provider declaration in `providers` section required for auxiliary services
