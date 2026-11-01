## Deploy flow (Worker + D1)

**Critical**: `CLOUDFLARE_API_TOKEN` (from vault `cloudflare/api_token`) lacks D1 execute permissions. Use global key for D1 migrations:

```bash
# D1 migration
export CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)"
export CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com"
unset CLOUDFLARE_API_TOKEN
npx wrangler d1 execute scena-saas-db --remote --file d1/saas-pipeline-runs.sql

# Worker deploy (same auth)
npx wrangler deploy --config workers/api/wrangler.toml
```

**Verify after deploy**:
```python
import urllib.request
for path in ['/health', '/ping']:
    req = urllib.request.Request(f'https://api.walter-ai.cloud{path}', headers={'User-Agent': 'Scena/1.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        print(f'{path} → {r.status}')
```

## Cloudflare Setup

### Wrangler Authentication (Global API Key)
```bash
CLOUDFLARE_API_KEY=cfk_... CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com wrangler deploy
```
NOT `CLOUDFLARE_API_TOKEN` — Global API Key has full access.

### Secrets (via Cloudflare API, NOT wrangler.toml vars)
```python
# PUT https://api.cloudflare.com/client/v4/accounts/{account}/workers/scripts/{name}/secrets
body = {"name": "OPENROUTER_API_KEY", "text": "sk-or-...", "type": "secret_text"}
```

### D1 Schema (tables)
- `clients` — matricule, name, telegram_bot_token, state, context, summary, portfolio, credits
- `video_jobs` — client_id, input_prompt, input_image_urls, status, piapi_task_id, output_url
- `image_jobs` — client_id, input_prompt, style, status, output_url
- `voice_jobs` — client_id, input_text, emotion, status, output_url
- `credit_ledger` — client_id, type, amount, balance_after
- `agent_log` — client_id, role, content, tool_name

## Deployment

```bash
# Global API Key auth (required for full Workers/D1 access)
CLOUDFLARE_API_KEY=cfk_... CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com npx wrangler deploy

# D1 remote queries (without --remote it hits local sqlite)
npx wrangler d1 execute scena-db --remote --command "SELECT * FROM clients"
npx wrangler d1 execute scena-db --remote --json --command "SELECT COUNT(*) FROM clients"

# Secrets list
npx wrangler secret list --name scena-api
```

### DNS Routing
- `admin-scena.walter-ai.cloud` → CNAME to scena-admin.pages.dev (Pages)
- `scena.walter-ai.cloud` → CNAME to scena.pages.dev (Pages)
- `api.walter-ai.cloud` → CNAME to Cloudflare Tunnel (VM), NOT the Worker
- Worker is also accessible at `scena-api.lucas-jouvencon.workers.dev`
- To route `api.walter-ai.cloud` to the Worker instead: add a Worker route in CF dashboard or use `wrangler` route commands

## Debugging D1 Without Wrangler Auth

When `wrangler d1 execute --remote` fails with "set CLOUDFLARE_API_TOKEN", query D1 directly via REST API using the **Global API Key** (`cfk_...`), NOT the API token (`cfut_...`).

**Critical distinction**:
- `CLOUDFLARE_API_TOKEN` (`cfut_...`) = fine-grained token. Works for Worker deploys, secrets, Pages. **Does NOT work for D1 REST API** → returns `403` with error `7403` ("account not authorized for this service").
- `CLOUDFLARE_API_KEY` (`cfk_...`) = Global API Key. Has full access including D1 REST API.

```python
import requests

CF_API_KEY = "cfk_..."       # Global API Key, NOT cfut_ token
CF_EMAIL = "lucas.jouvencon@gmail.com"
ACCOUNT_ID = "{{bw:W.Alter · cloudflare:field:account_id}}"
DB_ID = "3567d347-37d7-45d5-b348-3dfc5f674006"

url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}/query"
headers = {
    "X-Auth-Email": CF_EMAIL,
    "X-Auth-Key": CF_API_KEY,     # ← cfk_... required
    "Content-Type": "application/json"
}
payload = {"sql": "SELECT * FROM video_jobs ORDER BY rowid DESC LIMIT 10"}
resp = requests.post(url, headers=headers, json=payload)
data = resp.json()
# data["result"][0]["results"] = list of rows as dicts
```

Use this to inspect stuck jobs, check error messages, and verify piapi_task_id/status without needing a properly configured wrangler CLI.
