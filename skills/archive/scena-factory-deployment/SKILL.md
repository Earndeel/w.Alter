---
name: scena-factory-deployment
description: Deploy and configure the Scena Factory multi-tenant video agent SaaS platform — Cloudflare tunnels, Pages, Clerk auth, Stripe, admin dashboard.
triggers:
  - "deploy scena"
  - "cloudflare tunnel hermes-workspace.com"
  - "clerk auth integration"
  - "scena factory setup"
  - "landing page deploy"
---

# Scena Factory Deployment Guide

## Architecture
- Landing page → Cloudflare Pages (`scena.hermes-workspace.com`)
- Admin dashboard → Cloudflare Named Tunnel (`admin-scena.hermes-workspace.com`)
- Webhook API → Cloudflare Named Tunnel (`api.hermes-workspace.com`)
- Client dashboards → Cloudflare Tunnels per client (`dashboard-{id}.hermes-workspace.com`)
- All services on VM, tunnel via systemd service

## Cloudflare Named Tunnel (NOT quick tunnels for custom domains)

Quick tunnels (`cloudflared tunnel --url`) give `trycloudflare.com` URLs that change on restart. Custom domains require named tunnels.

### Setup steps:
1. Create tunnel via API: `POST /accounts/{id}/cfd_tunnel` with `{"name": "scena-main"}`
2. Get credentials from response `credentials_file` field — save to `~/.cloudflared/{tunnel_id}.json`
3. Write config at `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: <tunnel_id>
   credentials-file: /root/.cloudflared/<tunnel_id>.json
   ingress:
     - hostname: admin-scena.hermes-workspace.com
       service: http://localhost:5050
     - hostname: api.hermes-workspace.com
       service: http://localhost:5051
     - service: http_status:404
   ```
4. Create CNAME DNS records pointing to `{tunnel_id}.cfargotunnel.com`
5. Start with: `cloudflared tunnel --config ~/.cloudflared/config.yml run`

### Pitfalls discovered:
- **Credentials from GET endpoint are empty** — must capture from POST create response
- **CNAME to trycloudflare.com does NOT work** — must use named tunnel with `cfargotunnel.com`
- **Services must listen on 0.0.0.0**, not 127.0.0.1, for tunnel to reach them
- **Python http.server returns 000** sometimes — restart usually fixes it

### Systemd service for persistence:
```ini
# /etc/systemd/system/scena-tunnel.service
[Unit]
Description=Cloudflare Tunnel for Scena
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --config /root/.cloudflared/config.yml run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Cloudflare Pages
1. Create project via API: `POST /accounts/{id}/pages/projects` with `{"name": "scena", "production_branch": "main"}`
2. Deploy: `npx wrangler pages deploy ./landing --project-name scena`
3. Add custom domain: `POST /accounts/{id}/pages/projects/scena/domains` with `{"name": "scena.hermes-workspace.com"}`
4. Delete old tunnel CNAME for scena — Pages handles its own routing

### Pitfall: Token needs Pages permission
The API token must include `Account → Cloudflare Pages → Edit` or deployment fails with `Authentication error [code: 10000]`.

## Clerk Auth Integration
- Publishable key goes in landing page HTML (client-side)
- Secret key used server-side for API calls (but blocked by Cloudflare from server — use frontend SDK only)
- Key format: `pk_test_<base64_encoded_domain>` where domain is like `pleasing-bedbug-9.clerk.accounts.dev`
- Mount widget: `window.Clerk.mountSignIn(element)`
- After auth, call backend `/api/signup` with `clerk_id`, `name`, `email`

## Admin Dashboard Auth
- Login page at `/` (login.html), dashboard at `/dashboard`
- Flask middleware in `admin/auth.py` with `setup_auth(app)`
- Session tokens in memory (24h TTL), cookie-based
- Public routes: `/health`, `/webhook/stripe`, `/api/signup`
- Credentials via env vars: `ADMIN_USER`, `ADMIN_PASS`

## Service Ports
- 5050: Admin dashboard
- 5051: Webhook server (Stripe + signup)
- 8080: Landing page (fallback, before Pages deploy)

## DNS Records (zone: hermes-workspace.com)
```
CNAME scena       → scena.pages.dev          (Pages)
CNAME admin-scena → {tunnel_id}.cfargotunnel.com (Tunnel)
CNAME api         → {tunnel_id}.cfargotunnel.com (Tunnel)
CNAME www         → hermes-workspace.com          (Redirect)
```

## Environment (.env at /root/projects/video-agents-factory/.env)
```
CLOUDFLARE_API_TOKEN=cfut_...
CLOUDFLARE_ACCOUNT_ID=12ee2e...
CLOUDFLARE_ZONE_ID=ba01ee...
FAL_KEY=30529a...
OPENROUTER_API_KEY=sk-or-v1-...
STRIPE_SECRET_KEY=sk_live_...
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

## Client Dashboard URLs (Matricule System)
Client dashboards use matricule-based URLs instead of names for privacy:
```
dashboard-lucas.hermes-workspace.com  →  app-sc0002.hermes-workspace.com
```
- Matricule auto-generated: `sc0001`, `sc0002`, etc.
- Stored in admin DB `clients.matricule` column
- CNAME: `app-sc0002` → `{tunnel_id}.cfargotunnel.com`
- Tunnel ingress routes `app-sc0002.hermes-workspace.com` → `localhost:{client_port}`

## Bot Pool Management
Telegram @BotFather has NO API for creating bots. Workaround:
1. Pre-create 10-20 bots via @BotFather manually
2. Store tokens in `bot_pool.db` (table: bot_pool)
3. On client signup → assign next available bot from pool
4. CLI: `python3 bot_pool.py add --token "123:ABC" --name "Slot 1"`

## Clerk Auth Pitfalls (v5)
1. **SDK must load from instance domain**, not generic CDN:
   ```js
   // WRONG: https://cdn.jsdelivr.net/npm/@clerk/clerk-js@latest/...
   // RIGHT: https://{CLERK_DOMAIN}/npm/@clerk/clerk-js@5/dist/clerk.browser.js
   // FALLBACK: https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js
   ```
2. `window.Clerk` may not be available immediately after script load — need polling (100ms intervals, up to 100 tries)
3. Call `await Clerk.load({publishableKey: PK})` before mounting widgets
4. Server-side API calls to `api.clerk.com` are blocked by Cloudflare (error 1010) from some IPs — use frontend SDK only

## Signup Flow
```
Clerk auth → landing page JS → POST /api/signup {name, email, clerk_id}
  ↓ webhook finds client by email first, then by clerk_id in notes
  ↓ if new: auto_provision (assign bot + create DB + start dashboard)
  ↓ if existing: return current bot + credits + dashboard URL
  ↓ response: {bot_link, bot_username, credits, dashboard_url}
```
Key: webhook must search by EMAIL before creating new client (prevents duplicates on re-login).

## Agent Tool-Calling Architecture
Scena agent uses a tool-calling pattern (not a state machine):
1. System prompt lists all available tools with JSON format examples
2. LLM decides: respond in text OR call a tool via `{"tool": "name", "params": {...}}`
3. Agent executes tool, appends result to conversation
4. LLM reads tool result and generates natural response
5. All tool calls saved to persistent memory

Tools available: `analyze_image`, `analyze_video`, `generate_image`, `generate_video`, `estimate_cost`, `create_character`, `generate_character`, `list_characters`, `remember`, `recall`, `check_balance`, `get_time`

## LLM Per-Step Configuration
Models used for each pipeline step stored in admin DB `model_config` table:
- `analysis` — understanding client intent
- `planning` — creating action plans
- `payload_gen` — generating API payloads
- `conversation` — agent chat responses
- `image_analysis` — image/frame description

Configurable from admin dashboard "LLM Config" tab. Agents read config on each run (no restart needed).

## CORS for Cross-Subdomain APIs
Landing page on `scena.hermes-workspace.com` calling API on `api.hermes-workspace.com` requires CORS headers on Flask:
```python
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response
```

## Cloudflare Serverless Architecture (New — replaces VM/tunnel approach)

The new architecture migrates from Flask on VM to fully Cloudflare-native:

```
scena-cloudflare/
├── workers/api/
│   ├── src/index.ts      ← Main Worker (webhooks, API, D1 queries)
│   └── wrangler.toml     ← D1 binding, env vars, routes
├── d1/
│   └── schema.sql        ← Tables: clients, credit_ledger, video_jobs
├── pages/admin/          ← Admin dashboard (Cloudflare Pages)
└── pages/landing/        ← Landing page (Cloudflare Pages)
```

### D1 Database Setup
```bash
# Create D1 database
CLOUDFLARE_API_KEY=cfk_... CLOUDFLARE_EMAIL=... wrangler d1 create scena-db
# → returns database_id

# Apply schema
wrangler d1 execute scena-db --file=d1/schema.sql --remote
```

### Multi-Tenant Telegram Webhook Routing (KEY PATTERN)

Each client's bot webhook URL includes their matricule:
```
https://api.hermes-workspace.com/webhook/telegram/{matricule}
```

Flow:
1. Client provides their own bot token via `POST /api/bot/validate`
2. Worker calls Telegram API to set webhook: `setWebhook(url=".../webhook/telegram/sc0001")`
3. When Telegram sends update → Worker extracts `sc0001` from URL → queries D1 for that client's config
4. Worker responds using the client's bot token

This single Worker handles ALL clients — no per-client infrastructure needed.

### Wrangler Auth with Global API Key

The Global API Key (`cfk_...`) requires TWO env vars:
```bash
CLOUDFLARE_API_KEY=«secret:vault»
CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com
```

NOT `CLOUDFLARE_API_TOKEN` (that's for scoped tokens `cfut_...`).

### Worker Deployment
```bash
CLOUDFLARE_API_KEY=cfk_... CLOUDFLARE_EMAIL=... wrangler deploy
# → deploys to scena-api.lucas-jouvencon.workers.dev
```

### Custom Domain Route
```python
# Via API — add route to zone
POST /zones/{zone_id}/workers/routes
{"pattern": "api.hermes-workspace.com/*", "script": "scena-api"}
```

### Pages Deployment
```bash
# Create project
wrangler pages project create scena-admin --production-branch main

# Deploy
wrangler pages deploy ./pages/admin --project-name scena-admin

# Custom domain (if not using tunnel)
POST /pages/projects/scena-admin/domains
{"name": "admin-scena.hermes-workspace.com"}
```

### D1 Schema (multi-tenant)
```sql
-- Clients with their own bot
CREATE TABLE clients (
    id INTEGER PRIMARY KEY,
    matricule TEXT UNIQUE NOT NULL,    -- sc0001, sc0002...
    name TEXT, email TEXT,
    telegram_bot_token TEXT DEFAULT '',
    telegram_bot_username TEXT DEFAULT '',
    credits REAL DEFAULT 0,
    status TEXT DEFAULT 'active'
);

-- Video jobs (async generation)
CREATE TABLE video_jobs (
    id INTEGER PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    status TEXT DEFAULT 'pending',     -- pending, processing, completed, failed
    input_prompt TEXT,
    input_image_urls TEXT,             -- JSON array
    piapi_task_id TEXT,
    output_url TEXT,
    telegram_chat_id TEXT              -- for sending result back
);
```

### Endpoints (Cloudflare Worker)
```
GET  /health                          → {"status":"ok"}
GET  /ping                            → {"pong":true}
POST /api/register                    → create client, auto matricule
POST /api/bot/validate                → validate TG token + set webhook
POST /webhook/telegram/{matricule}    → multi-tenant TG handler
GET  /api/client/{matricule}/stats    → client dashboard data
GET  /api/admin/stats                 → global stats
GET  /api/admin/clients               → list all clients
POST /webhook/stripe                  → credit purchases
```

### Key Learnings
1. Cloudflare scoped tokens need specific permissions — Zone.DNS.Edit + Cloudflare Tunnel for tunnels, Pages.Edit for deployments
2. Flask `template_folder` path must be relative to `__file__` location, not CWD
3. Named tunnels require credentials from the POST create response, not GET detail
4. The `.env` file search path in modules must account for the module's location relative to the project root (2-3 levels of dirname depending on module depth)
5. Python HTTP server (http.server) can return empty responses through Cloudflare tunnel — production Flask apps work fine
6. Quick tunnels (trycloudflare.com) are unreliable — use named tunnels for anything permanent
7. Bot pool must exist before client signup works — pre-create bots via @BotFather
8. Always search by email first in signup flow to prevent duplicate client creation
9. **Wrangler Global API Key auth**: Use `CLOUDFLARE_API_KEY` + `CLOUDFLARE_EMAIL` env vars (NOT `CLOUDFLARE_API_TOKEN` which is for scoped tokens)
10. **Multi-tenant webhook routing**: Embed matricule in webhook URL path — single Worker serves all clients, D1 lookup per request
11. **D1 is SQLite-based**: Same SQL syntax, but runs on Cloudflare edge — no connection management needed, queries are stateless

## PiAPI Integration (replaces Fal.ai)

### Unified API Schema
All models via one endpoint:
```
POST https://api.piapi.ai/api/v1/task
Header: X-API-Key: <key>, User-Agent: Scena/1.0

{
  "model": "seedance-2-fast",
  "task_type": "video_generation",
  "input": {
    "prompt": "...",
    "duration": 5,
    "aspect_ratio": "9:16",
    "mode": "text_to_video"
  },
  "config": {
    "webhook_config": {
      "endpoint": "https://api.hermes-workspace.com/webhook/piapi"
    }
  }
}
```

### Status check
```
GET https://api.piapi.ai/api/v1/task/{task_id}
Header: X-API-Key: <key>, User-Agent: Scena/1.0
```

Status values: `completed`, `processing`, `pending`, `failed`, `staged`

### Video output extraction
```typescript
const output = data.data.output;
const videoUrl = output.video_url
  || output.works?.[0]?.video?.resource_without_watermark
  || output.works?.[0]?.video?.resource;
```

### Pricing (Seedance 2.0 Fast)
- $0.10/second
- 5s = $0.50, 10s = $1.00, 15s = $1.50

### Pitfall: User-Agent required
Cloudflare blocks requests to PiAPI without a User-Agent header. Always include `"User-Agent": "Scena/1.0"` or curl will work but Python/TS fetch will get 403.

## Async Video Generation (Zero-Queue Pattern)

Uses PiAPI's native webhook callback instead of Cloudflare Queues:

```
1. Telegram message → Worker creates job in D1 (status=processing)
2. Worker calls PiAPI with webhook_config pointing to /webhook/piapi
3. Worker responds to Telegram immediately: "Rendu en cours 🍿"
4. PiAPI generates video (1-3 min)
5. PiAPI hits /webhook/piapi with result
6. Worker updates D1 (status=completed), sends video to Telegram via sendVideo
```

Key: Worker ALWAYS responds to Telegram in <3 seconds. The long wait happens externally.

## Zero-Storage Media Proxy

NEVER give PiAPI direct Telegram URLs (they contain the bot token). Instead:

```
Proxy URL: https://api.hermes-workspace.com/proxy/media/{file_id}?client={matricule}
```

The proxy route:
1. Looks up client's bot token from D1 by matricule
2. Calls Telegram getFile to get the file path
3. Streams the file directly from Telegram to PiAPI (zero storage)

```typescript
async function handleMediaProxy(env, fileId, matricule) {
  const client = await env.DB.prepare(
    "SELECT telegram_bot_token FROM clients WHERE matricule = ?"
  ).bind(matricule).first();

  const getFileResp = await fetch(
    `https://api.telegram.org/bot${client.telegram_bot_token}/getFile?file_id=${fileId}`
  );
  const filePath = (await getFileResp.json()).result.file_path;

  const fileResp = await fetch(
    `https://api.telegram.org/file/bot${client.telegram_bot_token}/${filePath}`
  );

  return new Response(fileResp.body, {
    headers: {
      "Content-Type": fileResp.headers.get("Content-Type") || "image/jpeg",
      "Cache-Control": "public, max-age=3600"
    }
  });
}
```

Store only `file_id` + proxy URL in D1, never the Telegram URL with token.

## Agent Brain (Multi-Modal State Machine)

### D1 Schema (agent columns on clients table)
```sql
ALTER TABLE clients ADD COLUMN state TEXT DEFAULT 'idle';
ALTER TABLE clients ADD COLUMN context TEXT DEFAULT '[]';
ALTER TABLE clients ADD COLUMN summary TEXT DEFAULT '';
ALTER TABLE clients ADD COLUMN portfolio TEXT DEFAULT '[]';
```

States: `idle`, `waiting_image`, `waiting_video`, `waiting_voice`, `consulting`

### Tool Calling with Mimo v2 Pro (via OpenRouter)
```typescript
const resp = await fetch("https://openrouter.ai/api/v1/chat/completions", {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${OPENROUTER_API_KEY}`,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    model: "xiaomi/mimo-v2-pro",
    messages: [
      { role: "system", content: systemPrompt },
      ...context,
      { role: "user", content: userMessage }
    ],
    tools: SCENA_TOOLS,  // JSON Schema function definitions
    tool_choice: "auto",
    temperature: 0.3,
    max_tokens: 2000
  })
});
```

### System Prompt Pattern (Consultant vs Executor)
- Vague input ("fais une vidéo") → respond with text consultation, NO tool call
- Specific input (description + style + image ref) → call generate_video tool
- Always ask validation after media delivery
- Use `/reset` command to clear project state

### Rolling Summary (Cost Control)
When context exceeds 8 messages, compact:
```typescript
// Call LLM to summarize the conversation
const summary = await callLLM(
  `Résume factuellement: ${JSON.stringify(context)}. Existant: ${existingSummary}`
);
// Reset context, keep summary
await updateClientState(clientId, "idle", [], summary, portfolio);
```

### Project Completion
```typescript
// Tool: mark_project_complete
// Moves final media URL to portfolio, clears context/summary, resets to idle
await env.DB.prepare(
  `UPDATE clients SET state='idle', context='[]', summary='', portfolio=? WHERE id=?`
).bind(JSON.stringify([...portfolio, {url, type, date}]), clientId).run();
```

## Client Provides Own Bot (No Pool)
1. Client creates bot via @BotFather
2. Client sends token to `POST /api/bot/validate` with their matricule
3. Worker validates token with Telegram getMe
4. Worker sets webhook: `setWebhook(url="https://api.hermes-workspace.com/webhook/telegram/{matricule}")`
5. Worker saves token to D1

No bot pool needed — each client manages their own bot.

## Wrangler Secret Management (via Cloudflare API)
When wrangler CLI fails with Global API Key, use direct API:
```python
# Set secret via API
PUT /accounts/{id}/workers/scripts/{name}/secrets
{"name": "OPENROUTER_API_KEY", "text": "sk-or-...", "type": "secret_text"}
```

Cannot have both `[vars]` in wrangler.toml AND secrets with same name — remove from vars first.
