---
name: cloudflare-worker-deploy-curl
description: Deploy Cloudflare Workers via curl when wrangler's Node.js fetch fails (sandbox/CI environments). Uses wrangler dry-run to bundle, then uploads via CF REST API.
---

# Cloudflare Worker Deploy via curl

> **Credentials — read this first (fixed 2026-10-04).** Never type or guess Cloudflare credentials. Run every
> Cloudflare command through `/root/.hermes/scripts/walter-cloudflare -- <command>`, which injects
> `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_EMAIL`, `CLOUDFLARE_API_KEY` (global key), `CLOUDFLARE_API_TOKEN` and
> `CLOUDFLARE_AI_TOKEN` without printing them; `walter-cloudflare check` verifies them all.
> Pitfall that cost a debugging round: the vault item « W.Alter · cloudflare » has **no e-mail field**; the account
> e-mail lives in `~/.hermes/.env` as `CLOUDFLARE_EMAIL`. The `user@example.com` below is only an example — a global
> key used with it answers « Unknown X-Auth-Key or X-Auth-Email » (403) / « Authentication error » (401).
> The vault `api_token` has no Workers AI permission; Workers AI uses `CLOUDFLARE_AI_TOKEN` (scoped « Workers AI Read »).

## When to use
- `wrangler deploy` fails with `fetch failed` (Node.js networking issues in sandbox/container)
- CI environments where wrangler can't reach CF API
- Need to deploy programmatically without wrangler auth flow

## Steps

### 1. Bundle with wrangler dry-run
```bash
# credentials injected by the helper (example only: never write an e-mail or key here)
/root/.hermes/scripts/walter-cloudflare -- wrangler deploy --dry-run --outfile=/tmp/worker-bundle.js
```
This produces a pre-built multipart form body (not plain JS).

### 2. Deploy via curl
The outfile is already a complete multipart form. Extract the boundary from the first line and upload:

```python
import subprocess, json

# Extract boundary from first line
with open("/tmp/worker-bundle.js", "rb") as f:
    first_line = f.readline().decode()

boundary = first_line.strip()  # e.g. "------formdata-undici-073527868525"
content_type = f"multipart/form-data; boundary={boundary[2:]}"

result = subprocess.run([
    "curl", "-s", "-X", "PUT",
    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name}",
    "-H", f"X-Auth-Email: {email}",
    "-H", f"X-Auth-Key: {api_key}",
    "-H", f"Content-Type: {content_type}",
    "--data-binary", "@/tmp/worker-bundle.js",
    "--connect-timeout", "30",
    "--max-time", "120"
], capture_output=True, text=True, timeout=150)

data = json.loads(result.stdout)
print("Success:", data.get("success"))
```

### 3. Verify
```bash
curl -s https://your-worker.your-domain.com/health
```

## Authentication

Resolve Cloudflare credentials at runtime with `/root/.hermes/scripts/walter-cloudflare` (vault for the global key and
the vault token, `~/.hermes/.env` for the account id, the account e-mail and the Workers AI token); never embed
account e-mails, API keys or tokens in this skill. In Python, read them from the environment of a process started by
`walter-cloudflare -- python3 script.py`.

**Global API Key** (direct curl or Wrangler legacy authentication):
- Direct REST headers: `X-Auth-Email` and `X-Auth-Key`, populated from the vault.
- Wrangler env vars: `CLOUDFLARE_EMAIL` and `CLOUDFLARE_API_KEY`. This was verified with Wrangler 4.76.0 for remote D1 execution and Worker deployment.

**Scoped API Token** (preferred Wrangler authentication when available):
- Env var: `CLOUDFLARE_API_TOKEN`, populated from the vault.
- Do not put a Global API Key in `CLOUDFLARE_API_TOKEN`; use the legacy key/email pair above.

## D1 Binding in API
When uploading via REST API, D1 binding type is `"d1"` (NOT `"d1_database"`):
```json
{
  "bindings": [
    { "type": "d1", "name": "DB", "database_id": "..." }
  ]
}
```

## Pitfalls
- **`fetch failed` from wrangler** — Node.js can't reach CF API; use curl approach above
- **`binding has unknown type d1_database`** — use `"d1"` not `"d1_database"` in API metadata
- **`Invalid left-hand side`** — outfile is multipart form, not raw JS; send as `--data-binary` with boundary
- **`Unknown X-Auth-Key`** — Global API Key may be expired; generate new one at CF dashboard
- **Wrangler auth with Global API Key** — doesn't work; must use API Token for wrangler, Global API Key only works with direct curl
