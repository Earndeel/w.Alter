---
name: video-agent-factory
title: Video Agent Factory V2 — Multi-Client SaaS for AI Video Generation (Scena)
description: Multi-tenant platform with admin control plane, Stripe billing, supervisor, video extension, per-client Scena agents with Telegram, 4-stage pipeline, credit system, character sheets, and persistent memory. ⚠️ LEGACY V2 (Python/Flask). Active V3 is Cloudflare Workers in `scena-video-factory` skill. Clerk removed, Gemini replaced by Kimi/OpenRouter in V3.
---

# Video Agent Factory V2 — Scena Platform

**Location:** `/root/projects/video-agents-factory/`

Factory creates isolated client agents (Scena). Each client gets Telegram bot, dashboard, DB, credits, models. Admin panel manages everything centrally.

## Full Architecture

```
video-agents-factory/
├── factory.py                      ← CLI unified (create/list/credits/start/stop/health/stats/dashboard)
├── credits.py                      ← Legacy per-client credit system
├── shared/pricing.json             ← Fal.ai pricing × margin (1.5x), credit_value_usd=0.01
│
├── admin/                          ← V2: Central control plane
│   ├── admin_db.py                 ← Central DB: clients, credit_ledger, processes, error_log, stripe_events
│   ├── supervisor.py               ← Process management: start/stop/restart/health/auto-restart (max 5/hour)
│   ├── stripe_billing.py           ← Stripe: customers, checkout sessions, webhook processing
│   ├── telegram_provisioning.py    ← Bot validation, info retrieval, chat_id discovery
├── dashboard/                  ← Admin web UI (port 5050) — 6 tabs: Overview, Clients, Integrations, Models, Settings, Errors
│       ├── run.py              ← Flask: /api/stats, /api/clients, /api/integrations/status, /api/models/fal, /api/models/openrouter, /api/settings/keys, /api/settings/pricing
│       └── templates/index.html
├── integrations/
│   ├── cloudflare.py           ← Tunnels, DNS CNAME, zones, token validation
│   ├── openrouter.py           ← Key validation, model listing (352 models), credit check, recommended models
│   └── fal.py                  ← Key validation, curated endpoint catalog (video/image/audio/lipsync), cost estimation
│
└── client_template/                ← Copied per client
    ├── agent.py                    ← 🧠 Scena — pipeline-driven Telegram agent
    ├── persona.md                  ← Scena persona (concise, asks questions, professional)
    ├── memory.py                   ← Persistent memory: preferences, projects, characters, style_notes
    ├── pipeline/
    │   ├── orchestrator.py         ← 4-stage pipeline: Analyse → Plan → Generate → Polish
    │   ├── analyzer.py             ← Stage 1: Gemini 3.1 Pro → StructuredNeed JSON
    │   ├── planner.py              ← Stage 2: Gemini 3.1 Pro → ActionPlan with cost
    │   ├── generator.py            ← Stage 3: LLM payload gen → Fal.ai submit
    │   └── extender.py             ← Video extension: I2V chaining for >15s (last-frame extraction)
    ├── tools/
    │   ├── media.py                ← Video/image analysis, frame extraction via ffprobe/ffmpeg
    │   ├── generator.py            ← Video generation via fal_client
    │   ├── image_gen.py            ← Image gen (FLUX Pro/Dev, SDXL, Ideogram) + prompt enhancement
    │   ├── characters.py           ← Character sheet creation, storage, preview generation
    │   └── postprocess/
    │       └── postprocessor.py    ← Stage 4: ffmpeg (subtitles, filters, concat), TTS, lipsync
    ├── dashboard/                  ← Per-client Flask dashboard (dynamic port 5100+)
    ├── models/                     ← config.json + prompt.md + schema.md per model
    ├── db/pipeline.db              ← Isolated SQLite
    ├── assets/                     ← Client uploads
    └── characters/                 ← Character sheets (meta.json + prompt_sheet.md)
```

## 4-Stage Pipeline

**LLM stages 1-2:** `google/gemini-3.1-pro-preview` (deep analysis/planning)
**LLM payload gen:** `google/gemini-3-flash-preview` (fast payload generation)
**LLM conversation:** `xiaomi/mimo-v2-pro` (Nous Portal, free)

### Stage 1: Analyse (analyzer.py)
- Input: client message + assets + memory context
- Uses Gemini vision for image/video analysis
- Output: StructuredNeed {intent, summary, details, assets_analysis, questions_for_client, confidence}
- If confidence < 0.7 → Scena asks 2-3 clarifying questions, waits for answers, re-analyzes

### Stage 2: Planification (planner.py)
- Input: StructuredNeed + available models + credit balance
- Output: ActionPlan {steps[], estimated_total_credits, fits_budget, post_processing[], risks[]}
- Knows about video_extension for >15s content
- Client must confirm before execution

### Stage 3: Génération (generator.py)
- Handles: video_generation, video_extension, image_generation, character_creation
- LLM generates payload conforming to model schema
- Submits to Fal.ai, extracts URLs

### Stage 4: Fignolage (postprocessor.py)
- **subtitle_burn**: auto-timed SRT + ffmpeg burn-in
- **ffmpeg_filter**: color grade, speed, crop, fade, blur
- **audio_generation**: Edge TTS (free), extensible to ElevenLabs
- **lipsync**: audio replace (extensible to Wav2Lip/SadTalker)
- **concat_clips**: merge segments

## Video Extension (extender.py)

For videos > 15s (model max):
1. Generate first segment (T2V)
2. Extract last frame via ffmpeg
3. Upload frame to Fal.ai
4. Generate next segment (I2V with last frame)
5. Repeat until target duration
6. Concatenate all segments

Cost: `target_duration / 15 × per_segment_cost`

## Scena Persona

- Name: **Scena**
- Concise: 2-4 sentences max unless client asks for details
- Asks clarifying questions if demand is vague (format, duration, style, subject)
- Always estimates cost + asks confirmation before credit-consuming actions
- Stays on media creation topic only
- Professional freelance tone: "Bien noté.", "OK, ~X crédits ? Confirme ?"
- Remembers past projects, preferences, characters

## Credit System (admin_db.py — central)

- 1 credit = $0.01 USD
- Margin multiplier: 1.5x (configurable in pricing.json)
- Central ledger in admin.db (source of truth)
- Auto-sync to per-client DB
- Transaction types: purchase, charge, bonus, refund

## Admin DB Schema

```sql
clients        -- client_id, name, email, telegram_token/username, status, stripe_customer_id
credit_ledger  -- client_id, type, amount, balance_after, stripe_payment_id, endpoint
processes      -- client_id, process_type (agent/dashboard), pid, status, restart_count
error_log      -- client_id, source, level, message, resolved
stripe_events  -- event_id, event_type, client_id, amount, credits_added, processed
```

## Supervisor (supervisor.py)

- `ProcessManager` per client: start/stop/restart agent + dashboard
- Health check every 30s
- Auto-restart on crash (max 5 per hour)
- After 5 crashes → escalate to critical error
- All logged to admin DB error_log

## Stripe Integration (stripe_billing.py)

- `create_customer(client_id, name, email)`
- `create_checkout_session(customer_id, price_id, credits, success_url, cancel_url)`
- `process_webhook_event(event)` → returns {action, client_id, credits, amount_usd}
- `verify_webhook_signature(payload, sig_header)` for security
- Requires: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` in .env

## Telegram Provisioning (telegram_provisioning.py)

- `validate_token(token)` → bot info or None
- `get_bot_info(token)` → {bot_id, username, first_name}
- `discover_chat_id(token)` → latest chat_id from getUpdates
- `setup_client_bot(client_id, token, welcome_message)` → full setup
- Note: BotFather has no API for bot creation — tokens must be created manually

## Commands

```bash
python3 factory.py create --name "ClientX" --email "x@mail.com" --telegram-token "..." --credits 500
python3 factory.py list
python3 factory.py credits --client clientx --add 100
python3 factory.py credits --client clientx --ledger
python3 factory.py start --client clientx
python3 factory.py stop --client clientx
python3 factory.py restart --client clientx
python3 factory.py start-all
python3 factory.py health          # Check all processes, auto-restart if needed
python3 factory.py stats            # Global: clients, credits purchased/charged, errors
python3 factory.py errors           # Unresolved errors
python3 factory.py dashboard        # Admin web UI on port 5050
```

## Model Config (per client)

Each model = 3 files in `models/<model_id>/`:
- **config.json**: `{"name": "Kling v3 Pro", "endpoint": "fal-ai/kling-video/v3/pro/text-to-video"}`
- **prompt.md**: LLM instructions + rules (what to generate, constraints)
- **schema.md**: API reference (params, types, examples) — injected to LLM separately

Models can be added via client dashboard UI (⚙ Models button) or by copying files.

## API Keys (.env at `/root/projects/video-agents-factory/.env`)

```
FAL_KEY=...                          ← Fal.ai key (all clients share)
OPENROUTER_API_KEY=...               ← OpenRouter key (Scena's LLM access)
CLOUDFLARE_API_TOKEN=...             ← Cloudflare API token (scoped: Zone.DNS.Edit + Tunnel)
CLOUDFLARE_ACCOUNT_ID=...            ← Cloudflare account ID
STRIPE_SECRET_KEY=...                ← Stripe secret key (live)
STRIPE_WEBHOOK_SECRET=...            ← Stripe webhook secret
```

All 4 integrations (OpenRouter, Fal.ai, Cloudflare, Stripe) configured and verified as of 2026-04-08.

Keys can be set via:
1. Admin dashboard → Settings tab → save all keys at once
2. Manually edit `.env`
3. API: `PUT /api/settings/keys` with `{fal_key, openrouter_key, cloudflare_token, ...}`

## Admin Dashboard (port 5050)

6 tabs:
- **Overview**: Global stats + integration status dots (green/red)
- **Clients**: Card grid, click for detail modal (credits, ledger, errors, suspend/activate)
- **Integrations**: Cloudflare/OpenRouter/Fal/Stripe status with details
- **Models**: Browse Fal.ai endpoints (20+) and OpenRouter catalog (352 models)
- **Settings**: API keys entry + pricing config (margin, credit value, min purchase, Stripe price ID)
- **Errors**: Unresolved error list with resolve button

## Bot Pool (admin/bot_pool.py)

BotFather has NO API. Workaround: pre-create 10-20 bots, store tokens in pool DB, assign on signup.

```bash
# Add bots to pool
python3 admin/bot_pool.py add --token "123:ABC" --name "Slot 1"
python3 admin/bot_pool.py list

# On signup (automatic):
# assign_bot(client_id) → gets next available token → create_client(token=token)
```

Pool DB: `admin/bot_pool.db` — tracks status (available/assigned/disabled), assigned_to, assigned_at.

## DNS Management (admin/dns_manager.py)

Manages Cloudflare DNS zone for custom domains. Zone ID stored in `.env` as `CLOUDFLARE_ZONE_ID`.

```bash
python3 admin/dns_manager.py status     # Check zone status (pending/active)
python3 admin/dns_manager.py records    # List DNS records
python3 admin/dns_manager.py setup      # Create all standard records
python3 admin/dns_manager.py client-dns --client clientx --tunnel-url "https://xxx.trycloudflare.com"
```

For client dashboards: `dashboard-{client_id}.walter-ai.cloud` → CNAME to tunnel URL.

## Landing Page (landing/index.html)

Static HTML/CSS/JS landing page with:
- Hero with chat demo animation
- Features grid (6 capabilities)
- 4-stage pipeline visualization
- Models showcase
- Pricing tiers (Starter €10/1000cr, Pro €50/5000cr, Agency €200/25000cr)
- Signup form → POST to webhook server `/api/signup`

Deploy to Cloudflare Pages. Update `API_URL` in JS to point to webhook server.

Requires Cloudflare API Token with **Account → Cloudflare Pages → Edit** permission (in addition to existing permissions).

## Tailscale Access

Admin dashboard listens on `0.0.0.0:5050`, accessible via Tailscale IP:
```
http://100.91.35.121:5050
```

## Clerk Signup + Client Matching (webhook_server.py)

When Clerk creates a user, it sends a `clerk_id`. But the client may already exist (from manual creation or previous signup). The webhook MUST match by email first:

```python
# Find existing client by email
existing_client = None
if email:
    conn = get_admin_db()
    row = conn.execute("SELECT * FROM clients WHERE email = ?", (email,)).fetchone()
    conn.close()
    if row:
        existing_client = dict(row)

# Fallback: find by clerk_id in notes
if not existing_client and clerk_id:
    row = conn.execute("SELECT * FROM clients WHERE notes LIKE ?", (f"%clerk_id:{clerk_id}%",)).fetchone()
    if row:
        existing_client = dict(row)

# Use existing client_id or create new one
if existing_client:
    client_id = existing_client["client_id"]
```

Then `auto_provision()` must handle existing clients gracefully — just assign a bot if missing, don't try to recreate.

## Client Dashboard Access

Client dashboards run on dynamic ports (5100+). Access options:
- **Tailscale**: `http://100.91.35.121:{port}` — reliable, requires Tailscale on client device
- **Named tunnel**: per-client Cloudflare named tunnel — complex to set up dynamically
- **Quick tunnel**: `cloudflared tunnel --url http://localhost:{port}` — unstable, can't use custom domains

For MVP: use Tailscale. For production: pre-provision named tunnels per client.

## Landing Page Structure

- `/` — static landing (hero, features, pipeline, pricing) — no auth needed
- `/login.html` — dedicated Clerk auth page — simpler than embedding in landing
- All "Commencer"/"Créer mon agent" buttons link to `/login.html`
- After Clerk auth → portal shows bot link, credits, dashboard URL

## Pitfalls

- **Config id from directory name**, not file: `list_models()` injects `cfg['id'] = name`
- **Memory categories are plural**: `"preferences"`, `"projects"`, `"characters"` — NOT singular
- **Generation must NEVER auto-execute** — always gate behind client confirmation
- **PYTHONPATH**: dashboard imports need `sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))` AND `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))`
- **Admin DB path**: `os.path.dirname(os.path.dirname(ADMIN_DB))` for shared/pricing.json access
- **BotFather has no API** — bot tokens must be created manually via Telegram, then registered
- **Video extension**: I2V endpoint inferred from T2V by replacing `text-to-video` with `image-to-video`
- **Edge TTS**: needs `pip install edge-tts`
- **ffmpeg required** for all post-processing
- **Cloudflare**: needs API Token (not Global Key) with Zone.DNS.Edit + Cloudflare Tunnel permissions
- **Cloudflare scoped token**: `/user` returns 403. Use `/user/tokens/verify` then `/zones?per_page=1`
- **OpenRouter key for Scena** goes in factory `.env`, not per-client — all clients share the same LLM access
- **Flask template path**: if `run.py` is in `admin/dashboard/`, `ADMIN_DIR` is already `.../dashboard/`. Use `os.path.join(ADMIN_DIR, "templates")` NOT `os.path.join(ADMIN_DIR, "dashboard", "templates")`
- **Stripe .env path**: `admin/stripe_billing.py` needs 2x dirname (not 3x) to reach project root
- **Cron jobs** can check Cloudflare zone propagation status and auto-configure DNS when active
- **Cloudflare Pages deploy** requires wrangler: `npx wrangler pages deploy ./landing --project-name scena`

## V2 Additions (2026-04-08)

### Matricule System
Each client gets auto-incremented matricule (sc0001, sc0002...) instead of name in URLs.
```sql
ALTER TABLE clients ADD COLUMN matricule TEXT DEFAULT '';
-- Dashboard URL: https://app-sc0002.example.com
```
Dashboard URLs use matricule: `app-{matricule}.example.com`. No client name exposed.

### Clerk Auth (landing/login.html)
Clerk widget on dedicated `/login.html` page (doesn't work embedded in landing).
```html
<!-- Load from Clerk domain CDN, NOT jsdelivr -->
<script>
var s = document.createElement('script');
s.async = false;
s.setAttribute('data-clerk-publishable-key', CLERK_PK);
s.src = 'https://' + CLERK_DOMAIN + '/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
s.onload = function() {
    // MUST poll — window.Clerk not available on onload
    var iv = setInterval(function() {
        if (window.Clerk) { clearInterval(iv); initClerk(); }
    }, 100);
};
</script>
```
Key pitfall: jsdelivr CDN doesn't work. Use Clerk's own domain CDN.

### Bot Personality (persona.md)
- Sarcastic but professional
- Quick responses for basics (day, time, greetings) without LLM
- `/reset` command clears conversation state
- Images auto-prompt with "Analyse cette image" if no caption
- System prompt includes current date/time/day

### Stripe Dynamic Checkout (in client dashboard)
Create prices on the fly — no pre-created Price objects needed:
```python
# Price creation (form-encoded, NOT JSON)
price_data = urllib.parse.urlencode({
    "unit_amount": int(amount_usd * 100),
    "currency": "usd",
    "product_data[name]": f"Credits ({credits})",
}).encode()
```
Webhook at `api.example.com/webhook/stripe` adds credits to admin DB.

### Named Tunnel for All Services
Single tunnel, multiple hostnames:
```yaml
ingress:
  - hostname: admin-scena.example.com
    service: http://localhost:5050
  - hostname: api.example.com
    service: http://localhost:5051
  - hostname: app-sc0002.example.com
    service: http://localhost:5102
  - service: http_status:404
```
Systemd service for persistence. CNAME records point to `{tunnel_id}.cfargotunnel.com`.

### Webhook Server CORS
```python
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        return '', 204
```
Required because Clerk auth on `scena.example.com` calls `api.example.com`.

## Agent Tool-Calling Architecture (V3)

Scena is a proper tool-calling agent, NOT a state machine. The LLM decides which tools to use.

**Flow:**
```
Client message → LLM (with tool descriptions in system prompt)
  ↓ LLM responds: {"tool": "analyze_image", "params": {"file_path": "..."}}
  ↓ OR LLM responds in plain text (no tool needed)
Agent executes tool → appends result to conversation
LLM reads tool result → generates natural response
```

**Tools available to Scena:**
- `analyze_image` / `analyze_video` — visual analysis
- `generate_image` / `generate_video` — media generation (costs credits)
- `estimate_cost` — check cost before generating
- `create_character` / `generate_character` / `list_characters` — character sheets
- `remember` / `recall` — persistent memory
- `check_balance` / `get_time` — utilities

**Implementation:** `tools/scena_tools.py` — class `ScenaTools` with methods `tool_{name}(params)`. `get_tools_description()` generates the system prompt section. `execute_tool(name, params)` dispatches to the right method.

**Key:** The LLM sees tool descriptions WITH JSON format examples. It naturally learns to call tools. After tool execution, the result is fed back as a user message for the LLM to synthesize.

## LLM Per-Step Configuration (admin DB)

Models stored in `model_config` table, configurable from admin dashboard "LLM Config" tab:

| Step | Default Model | Purpose |
|------|--------------|---------|
| analysis | gemini-3.1-pro-preview | Understand client intent |
| planning | gemini-3.1-pro-preview | Create action plans |
| payload_gen | gemini-3.1-pro-preview | Generate API payloads |
| conversation | gemini-3.1-pro-preview | Agent chat responses |
| image_analysis | gemini-3-flash-preview | Describe images/frames |

Each pipeline module reads its model from admin DB on each call. No restart needed when changing models.

**API:** `GET /api/model-config` / `PUT /api/model-config` with `{analysis, planning, payload_gen, conversation, image_analysis}`.

## Matricule System

Each client gets auto-incremented matricule (`sc0001`, `sc0002`...) instead of name in URLs.

```sql
ALTER TABLE clients ADD COLUMN matricule TEXT DEFAULT '';
```

**Dashboard URLs:** `https://app-sc0002.example.com` — no client name exposed.

**Tunnel config:** Each client gets an ingress rule:
```yaml
- hostname: app-sc0002.example.com
  service: http://localhost:5102
```

**Webhook auto-generates matricule** on first signup and creates DNS CNAME + tunnel ingress rule.

## Bot Personality (persona.md)

Scena has a defined personality:
- Sarcastic but professional ("Concentre-toi. Vidéo, image, ou character sheet.")
- Quick handlers for basics (greetings, day/time) WITHOUT LLM — returns random responses
- `/reset` clears conversation state and project tracking
- Images auto-prompted with "Analyse cette image" if no caption
- System prompt includes current date/time/day for temporal awareness
- Asks ONE focused question when demand is vague, not a wall of questions

### New Pitfalls
- **Clerk SDK from jsdelivr doesn't work** — use domain CDN
- **`window.Clerk` not on script onload** — poll with setInterval
- **Stripe uses form-encoded, not JSON** — `urllib.parse.urlencode()`
- **`CLIENTS_DIR` not auto-inherited** — must define in webhook_server.py
- **`get_admin_db()` must be imported** — easy to forget
- **Flask debug=True breaks subprocess** — use `debug=False, threaded=True`
- **`base64.b64decode` needs padding** — `val + '=' * (4 - len(val) % 4)`
- **DNS propagation** — don't restart tunnel too fast, wait 10-15s
- **HTTP 000 = DNS not propagated yet** — wait
- **HTTP 530 = tunnel up but origin down** — check local service
- **HTTP 522 = DNS issue** — flush cache or wait
