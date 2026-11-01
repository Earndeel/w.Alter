## Architecture

```
/root/projects/video-agents-factory/
├── factory.py                      ← CLI (create/list/credits/start/stop/health/stats)
├── shared/pricing.json             ← Model costs × margin multiplier
│
├── admin/
│   ├── admin_db.py                 ← Central DB (clients, ledger, model_config, fal_endpoints, errors)
│   ├── supervisor.py               ← Process manager (auto-restart, health check)
│   ├── stripe_billing.py           ← Stripe (customers, checkout, webhooks)
│   ├── telegram_provisioning.py    ← Bot token validation
│   ├── bot_pool.py                 ← Pre-created Telegram bots pool
│   ├── tunnel_manager.py           ← Cloudflare tunnels
│   ├── dns_manager.py              ← DNS record management
│   ├── webhook_server.py           ← Stripe + Clerk signup webhooks (port 5051)
│   ├── auth.py                     ← Admin dashboard auth (session cookie, NO Basic Auth)
│   └── dashboard/                  ← Admin web UI (port 5050)
│       ├── run.py
│       └── templates/
│           ├── index.html          ← 8 tabs: Overview, Clients, Integrations, Models, Bots, LLM Config, Settings, Errors
│           └── login.html          ← Admin login page (dark theme)
│
├── landing/
│   ├── index.html                  ← Landing page (Cloudflare Pages)
│   └── login.html                  ← Client auth (Clerk SDK)
│
└── client_template/                ← Copied per client on signup
    ├── agent.py                    ← 🧠 Scena tool-calling agent
    ├── persona.md                  ← Personality (concise, sarcastic, pro)
    ├── memory.py                   ← Persistent client memory (JSON)
    ├── pipeline/
    │   ├── analyzer.py             ← Need analysis (reads model from DB)
    │   ├── planner.py              ← Action plan (reads model from DB)
    │   ├── generator.py            ← Payload gen (reads Fal endpoints from DB)
    │   ├── extender.py             ← Video extension (>15s via I2V last-frame)
    │   └── orchestrator.py         ← 4-stage orchestrator
    ├── tools/
    │   ├── scena_tools.py          ← Tool registry (LLM sees these)
    │   ├── media.py                ← Video/image analysis, frame extraction
    │   ├── generator.py            ← Video generation via Fal.ai
    │   ├── image_gen.py            ← Image generation
    │   ├── characters.py           ← Character sheet CRUD
    │   ├── asset_preprocessor.py   ← Upload to Fal.ai, frame extraction, model-specific formatting
    │   └── postprocess/
    │       └── postprocessor.py    ← ffmpeg (subtitles, filters), TTS, lipsync, concat
    ├── dashboard/                  ← Per-client Flask dashboard (unique port)
    ├── models/                     ← Per-client model configs
    ├── assets/                     ← Client uploads
    ├── characters/                 ← Character sheets
    ├── db/pipeline.db              ← Per-client SQLite
    └── memory.json                 ← Persistent memory
```

## Network Setup

### Cloudflare Named Tunnels (Production — NOT trycloudflare)

CNAME records CANNOT point to trycloudflare.com. Must use named tunnels with cfargotunnel.com.

```bash
# 1. Create tunnel via API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel" \
  -H "Authorization: Bearer {token}" \
  -d '{"name": "scena-main"}'
# → saves tunnel_id, credentials in result

# 2. Save credentials
# ~/.cloudflared/{tunnel_id}.json

# 3. Write config.yml
cat > /root/.cloudflared/config.yml << EOF
tunnel: {tunnel_id}
credentials-file: /root/.cloudflared/{tunnel_id}.json
ingress:
  - hostname: admin-scena.walter-ai.cloud
    service: http://localhost:5050
  - hostname: api.walter-ai.cloud
    service: http://localhost:5051
  - hostname: app-sc0002.walter-ai.cloud
    service: http://localhost:5102
  - service: http_status:404
EOF

# 4. Create CNAME records
# POST /zones/{zone_id}/dns_records
# {"type":"CNAME","name":"admin-scena","content":"{tunnel_id}.cfargotunnel.com","proxied":true}

# 5. Systemd service
cat > /etc/systemd/system/scena-tunnel.service << EOF
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
EOF
systemctl daemon-reload && systemctl enable scena-tunnel && systemctl restart scena-tunnel
```

### Clerk Auth (Client Portal) — REMOVED May 2026

**Clerk has been completely replaced by Better Auth.** All Clerk code, constants, JWKS verification, `clerk_id` column, and metadata references were removed on May 2, 2026. The content below is kept for historical reference only.

### Clerk Auth (Client Portal) — HISTORICAL
Clerk SDK MUST be loaded from jsdelivr — the Clerk domain CDN (`clerk.accounts.dev/npm/...`) doesn't serve the SDK.

```html
<script>
var CLERK_PK = 'pk_test_...';

// Load from jsdelivr (NOT from clerk.accounts.dev)
var s = document.createElement('script');
s.async = false;
s.src = 'https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
document.head.appendChild(s);

s.onload = function() {
    // Must POLL for window.Clerk — not available immediately on onload
    var iv = setInterval(function() {
        if (window.Clerk) {
            clearInterval(iv);
            initClerk();
        }
    }, 100);
};

async function initClerk() {
    await window.Clerk.load({publishableKey: CLERK_PK});
    if (window.Clerk.user) {
        showPortal(window.Clerk.user);
    } else {
        window.Clerk.mountSignIn(document.getElementById('clerk-mount'), {
            afterSignInUrl: window.location.href,
            afterSignUpUrl: window.location.href
        });
    }
}
</script>
```

Key lessons:
- **DO NOT** use `s.onload = function() { window.Clerk.load() }` — `window.Clerk` is undefined at that point
- **DO** poll with `setInterval` checking for `window.Clerk`
- **DO** use `cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js` (NOT clerk domain)
- After sign-in: call `/api/signup` with `clerk_id` + `name` + `email` → auto-provision bot + credits + matricule

### Bot Pool
Pre-create bots via @BotFather, store tokens in pool:
```bash
python3 bot_pool.py add --token "123:ABC" --name "Slot 1"
```
On signup, `assign_bot()` grabs next available → client gets `https://t.me/{username}`.

### Admin Auth (NO Basic Auth popup)
Custom login page with session cookie. The key fix: DON'T return `WWW-Authenticate: Basic` header — it triggers Chrome's native popup.

```python
@app.before_request
def before_auth():
    path = request.path
    # Public routes
    if path in ("/", "/api/auth/login", "/api/auth/logout", "/favicon.ico", "/health"):
        return None
    if not _is_authenticated(request):
        # API → JSON 401 (NO WWW-Authenticate header!)
        if path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        # Browser → redirect to login page
        return redirect("/")
```

Login page (`login.html`): dark themed form with username/password fields, inline error display (no `alert()`). On success: `document.cookie = 'scena_admin_token=' + token + ';path=/;max-age=86400'` then `window.location.href = '/dashboard'`.

## CLI Commands
```bash
python3 factory.py create --name "ClientX" --email "x@mail.com" --telegram-token "..." --credits 500
python3 factory.py agent --client clientx    # start agent
python3 factory.py start --client clientx    # start dashboard + tunnel
python3 factory.py credits --client clientx --add 500
python3 factory.py credits --client clientx --ledger
python3 factory.py list / health / stats / errors
python3 bot_pool.py add --token "..." --name "Slot 1"
python3 bot_pool.py list
```

## Production URLs
```
Landing:     https://scena.walter-ai.cloud       (Cloudflare Pages)
Login:       https://scena.walter-ai.cloud/login.html (Clerk)
Admin:       https://admin-scena.walter-ai.cloud  (tunnel, auth required)
Webhook:     https://api.walter-ai.cloud          (tunnel, public)
Dashboard:   https://app-sc000X.walter-ai.cloud   (tunnel, per client)
```

## API Keys (.env)
```
FAL_KEY=...
OPENROUTER_API_KEY=...
PIAPI_API_KEY=77a21faddd5fddbc661e26472dc1c482480c627c36fc08c96bcaf6573e33e197
CLOUDFLARE_API_TOKEN=cfut_...  (scoped, limited permissions)
CLOUDFLARE_GLOBAL_KEY=<secret retiré — clé globale Cloudflare : walter-cloudflare l'injecte (CLOUDFLARE_API_KEY)>  (full access)
CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com
CLOUDFLARE_ACCOUNT_ID={{bw:W.Alter · cloudflare:field:account_id}}
CLOUDFLARE_ZONE_ID=ba01ee08564dc4b2f66fa60b968a75f8
STRIPE_SECRET_KEY=...
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
ADMIN_USER=scena
ADMIN_PASS={{bw:admin-scena.walter-ai.cloud:password}}
```
