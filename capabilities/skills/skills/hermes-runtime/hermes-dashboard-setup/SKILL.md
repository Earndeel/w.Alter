---
name: hermes-dashboard-setup
description: >
  Set up and access the Hermes Agent web dashboard and API server.
  Covers gateway api_server platform configuration, API key setup,
  dashboard launch, and remote access via Tailscale.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [hermes, dashboard, api-server, gateway, web-ui]
    related_skills: [hermes-agent]
---

# Hermes Dashboard Setup

The Hermes web dashboard is a browser-based admin panel for managing config, sessions, skills, tools, and gateway status. It requires the `api_server` gateway platform to be running.

## When to Use

- User wants to access the Hermes web dashboard from a browser
- "Api_server disconnected" appears in the dashboard
- Setting up remote dashboard access (e.g., via Tailscale from a Mac)
- Configuring the gateway API server for external frontend integration

## Architecture

```
Browser -> dashboard origin (local, Tailscale, or Cloudflare Tunnel)
              |
         hermes dashboard frontend (default 9119; custom ports common)
              |
         React/Vite static files
              |
         http://localhost:8642 (api_server gateway platform)
              |
         Hermes Gateway process
```

The dashboard is a static frontend served by `hermes dashboard`. It connects to the gateway's `api_server` platform (port 8642) for real-time data. Without `api_server` running, the dashboard shows "Api_server disconnected".

For public Cloudflare Tunnel access, prefer the loopback-origin pattern in `references/cloudflare-tunnel-loopback-host-header.md`: bind dashboard to `127.0.0.1`, expose through cloudflared, and set `originRequest.httpHostHeader` to the loopback host/port so Hermes' Host-header protection accepts the request.

## Setup Steps

### 1. Generate and configure API_SERVER_KEY

Generate a secure random key via `hermes config set` or by storing it in the Hermes environment configuration. Use `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` to generate.

### 2. Enable the api_server platform

The api_server auto-enables when the key environment variable is present. Required env vars:

- `API_SERVER_ENABLED=true`
- `API_SERVER_HOST=127.0.0.1`
- `API_SERVER_PORT=8642`
- `API_SERVER_KEY=<your-generated-token>`

The gateway reads env vars directly (gateway/config.py lines 1489-1506). No config.yaml edit needed.

### 3. Restart the gateway

```bash
systemctl --user restart hermes-gateway.service
```

Verify with: `ss -tlnp | grep 8642` (should show LISTEN).

### 4. Launch the dashboard

```bash
hermes dashboard                          # localhost:9119
hermes dashboard --host 127.0.0.1 --insecure --no-open --port 8787  # loopback origin for tunnel/proxy
hermes dashboard --port 8080              # custom port
hermes dashboard --status                 # check if running
hermes dashboard --stop                   # stop
```

Avoid using `--host 0.0.0.0 --insecure` as the default remote-access pattern. Recent Hermes builds refuse public binds without a dashboard auth provider, and a systemd unit with `Restart=always` can create a CPU-heavy restart loop.

### 5. Remote access

Prefer one of these:

- Tailscale/SSH tunnel to a loopback-bound dashboard.
- Cloudflare Tunnel to a loopback-bound dashboard with `originRequest.httpHostHeader` matching the local origin host/port; see `references/cloudflare-tunnel-loopback-host-header.md`.
- A public bind only when a dashboard auth provider is configured.

## API Server Details

The `api_server` platform exposes an OpenAI-compatible API:

- `POST /v1/chat/completions` -- Chat Completions format
- `POST /v1/responses` -- Responses API format
- `GET /v1/models` -- List available models
- `GET /health` -- Health check
- `GET /api/sessions` -- List sessions

Default port: 8642. Authentication via API_SERVER_KEY header.

Compatible frontends: Open WebUI, LobeChat, LibreChat, AnythingLLM, NextChat.

## Dashboard REST API Endpoints

The dashboard web server (`hermes_cli/web_server.py`) exposes REST endpoints under `/api/`. Auth: Bearer token from `window.__HERMES_SESSION_TOKEN__` (extracted from the SPA HTML).

### Skills API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/skills` | List all skills (name, description, category, enabled) |
| GET | `/api/skills/{name}/content` | Read SKILL.md content + linked_files |
| PUT | `/api/skills/{name}/content` | Save SKILL.md content (body: `{"content": "..."}`) |
| PUT | `/api/skills/toggle` | Enable/disable skill (body: `{"name": "...", "enabled": true/false}`) |
| GET | `/api/skills/hub/search?q=...` | Search the skills hub |
| POST | `/api/skills/hub/install` | Install from hub |
| POST | `/api/skills/hub/uninstall` | Uninstall hub skill |
| POST | `/api/skills/hub/update` | Update hub skill |

### Adding Custom API Endpoints

In `hermes_cli/web_server.py` (FastAPI app):

```python
@app.get("/api/skills/{name}/content")
async def get_skill_content(name: str):
    from tools.skills_tool import skill_view
    import json as _json
    result = skill_view(name, preprocess=False)
    data = _json.loads(result)
    if not data.get("success"):
        return JSONResponse(data, status_code=404)
    return {"success": True, "content": data.get("content", ""), ...}
```

For PUT endpoints with a body, define a Pydantic model:
```python
class SkillContentUpdate(BaseModel):
    content: str

@app.put("/api/skills/{name}/content")
async def update_skill_content(name: str, body: SkillContentUpdate):
    ...
```

### Frontend API Client

In `web/src/lib/api.ts`, add methods to the `api` object:
```typescript
getSkillContent: (name: string) =>
  fetchJSON<ResponseType>(`/api/skills/${encodeURIComponent(name)}/content`),
```

## Building the Frontend

The frontend is a Vite + React app in `web/`. It's a monorepo workspace.

```bash
# Build (must use vite directly — tsc may not be in PATH)
cd /root/.hermes/hermes-agent/web
../node_modules/.bin/vite build

# Output goes to hermes_cli/web_dist/
```

**Pitfall:** `npm run build` runs `tsc -b && vite build` but `tsc` is often missing from the workspace. Use `../node_modules/.bin/vite build` directly to skip type-checking.

**Pitfall:** `vite build` may be detected as a long-lived process by the `terminal` tool. Use `execute_code` with `subprocess.run()` instead:
```python
subprocess.run(["../node_modules/.bin/vite/build"], cwd="/root/.hermes/hermes-agent/web", timeout=120)
```

After building, restart the dashboard to serve new assets.

## Restarting the Dashboard

```bash
hermes dashboard --stop    # kills existing processes (exit -15 is normal)
hermes dashboard --host 0.0.0.0 --insecure --no-open --port 9119
```

**Pitfall:** `hermes dashboard --stop` returns exit code -15 (SIGTERM). The terminal tool treats non-zero exit as failure. Use `execute_code` with `subprocess.run()` to avoid false error loops.

**Pitfall:** After stopping, the dashboard may take 3-5 seconds to fully release the port. Add a `sleep 2` between stop and restart.

## Desktop Apps — Two Distinct Projects

### Bootstrap Installer (apps/bootstrap-installer)
- Tauri 2 (Rust + WebKit), bundle ID `com.nousresearch.hermes.setup`, v0.0.1
- The `Hermes-Setup.dmg` — GUI wrapper around `scripts/install.sh`
- **arm64-only** — does NOT run on Intel Macs
- Source: `apps/bootstrap-installer/src-tauri/`

### Full Desktop App (apps/desktop)
- Electron + React (Vite), bundle ID `com.hermesdesktop.app`, v0.15.1+
- Universal binary (x86_64 + arm64) — works on Intel
- SSH connection management, TUI integration, chat, gateway RPC
- Download: https://hermes-agent.nousresearch.com/desktop
- Source: `apps/desktop/`

### Identifying Which App

```bash
# Bundle ID
/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' /Applications/Hermes.app/Contents/Info.plist

# Architecture
lipo -info /Applications/Hermes.app/Contents/MacOS/*
```

| Property | Bootstrap Installer | Full Desktop App |
|----------|-------------------|-----------------|
| Bundle ID | com.nousresearch.hermes.setup | com.hermesdesktop.app |
| Version | 0.0.1 | 0.9.0+ |
| Binary | arm64 only | universal |
| Framework | Tauri (Rust) | Electron (Node) |

**Pitfall**: DMG is just an installer, not the app. Skip it and run the install script directly. Intel Macs can't run the Tauri DMG (arm64-only). Use the Electron desktop app or the CLI. `hermes dashboard` replaces both native apps for most use cases.

## Dashboard Development — Adding Features

Every dashboard feature follows this 3-step pattern:

### 1. Backend endpoint in `web_server.py`

```python
@app.get("/api/skills/{name}/content")
async def get_skill_content(name: str):
    from tools.skills_tool import skill_view
    import json as _json
    result = skill_view(name, preprocess=False)
    data = _json.loads(result)
    if not data.get("success"):
        return JSONResponse(data, status_code=404)
    return {"success": True, "content": data.get("content", ""), ...}
```

For PUT/POST, use Pydantic models:
```python
class SkillContentUpdate(BaseModel):
    content: str

@app.put("/api/skills/{name}/content")
async def update_skill_content(name: str, body: SkillContentUpdate):
    # ... implementation ...
    return {"success": True}
```

Auth: endpoints behind `/api/*` require the session token as `Authorization: Bearer <token>`. The token is injected into the HTML as `window.__HERMES_SESSION_TOKEN__`.

### 2. Frontend API method in `web/src/lib/api.ts`

```typescript
getSkillContent: (name: string) =>
    fetchJSON<ResponseType>(`/api/skills/${encodeURIComponent(name)}/content`),
saveSkillContent: (name: string, content: string) =>
    fetchJSON<ResponseType>(`/api/skills/${encodeURIComponent(name)}/content`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
    }),
```

### 3. Frontend component in `web/src/pages/`

Add state, handlers, and UI. For a detail panel pattern (side drawer):
- State: `selectedItem`, `itemContent`, `loadingContent`, `editing`, `editContent`
- Panel: fixed overlay with `bg-black/40`, click-outside-to-close
- Footer toolbar for actions (Edit/Save/Cancel) — more visible than header buttons on split screens

### Building the Frontend

```bash
cd /root/.hermes/hermes-agent/web
node ../node_modules/vite/bin/vite.js build    # outputs to hermes_cli/web_dist/
hermes dashboard --stop                         # restart to pick up backend changes
hermes dashboard --host 0.0.0.0 --insecure --no-open --port 9119 --skip-build
```

Frontend changes need a vite build. Backend changes need a dashboard restart.

### Testing API Endpoints

```python
import requests, re
r = requests.get("http://127.0.0.1:9119/skills")
token = re.search(r'__HERMES_SESSION_TOKEN__="([^"]+)"', r.text).group(1)
headers = {"Authorization": f"Bearer {token}"}
requests.get("http://127.0.0.1:9119/api/skills", headers=headers)
```

## Creating Custom Dashboard Themes

The dashboard uses a 3-layer palette system: background (canvas), midground (accent/text), foreground (highlight). Every UI color is derived from these via CSS `color-mix()`.

### 1. Define the theme in `web/src/themes/presets.ts`

```typescript
export const myTheme: DashboardTheme = {
  name: "my-theme",
  label: "My Theme",
  description: "Description for the picker",
  palette: {
    background: { hex: "#000000", alpha: 1 },  // canvas color
    midground: { hex: "#03DFE8", alpha: 1 },    // primary accent — drives all derived colors
    foreground: { hex: "#D0FBFE", alpha: 0 },   // highlight layer (alpha 0 = invisible)
    warmGlow: "rgba(0, 0, 0, 0)",               // vignette overlay — use rgba(0,0,0,0) for none
    noiseOpacity: 0,                             // grain texture — 0 for pure flat
  },
  typography: { ...DEFAULT_TYPOGRAPHY, fontSans: `...`, fontMono: `...` },
  layout: { ...DEFAULT_LAYOUT, radius: "0.375rem" },
  terminalBackground: "#000000",
  colorOverrides: { primary: "#03DFE8", border: "#029BA8", ... },
  swatchColors: ["#000000", "#03DFE8", "#D0FBFE"],  // picker preview
};
```

Register in `BUILTIN_THEMES` at the bottom of the same file:
```typescript
export const BUILTIN_THEMES: Record<string, DashboardTheme> = {
  ...existing,
  "my-theme": myTheme,
};
```

### 2. Register in backend (`hermes_cli/web_server.py`)

Add to `_BUILTIN_DASHBOARD_THEMES` list (~line 7868):
```python
{"name": "my-theme", "label": "My Theme", "description": "..."},
```

### 3. Activate

```bash
hermes config set dashboard.theme my-theme
```

### Porting TUI skins to dashboard themes

TUI skin colors (from `~/.hermes/skins/*.yaml`) map to dashboard palette:
| TUI skin key | Dashboard palette |
|---|---|
| `status_bar_bg` | `palette.background.hex` (darken slightly) |
| `banner_accent` / `ui_accent` | `palette.midground.hex` |
| `banner_text` | `palette.foreground.hex` |
| `completion_menu_bg` | `colorOverrides.card` / `terminalBackground` |
| `completion_menu_current_bg` | hover/selection backgrounds |

### Theme palette pitfalls

- **`warmGlow` adds a color tint** over the entire background. Even `rgba(3, 223, 232, 0.15)` at 15% alpha is visible. Use `rgba(0, 0, 0, 0)` for a pure flat background.
- **`noiseOpacity > 0` adds grain texture**. Set to 0 for a clean look.
- **`midground` drives everything** — primary, accent, border, card, muted, ring are all derived from it via `color-mix()`. A bright midground on a dark background will tint cards, borders, and muted areas.
- **`colorOverrides` escape hatch** — when the derived colors don't look right, pin specific shadcn tokens here (e.g. `card`, `border`, `muted`).
- **CSS derivation** lives in `web/src/index.css` — look for `--color-card`, `--color-muted`, `--color-border` to understand how palette maps to UI.

## Cloudflare Tunnel Pattern

When exposing the dashboard through Cloudflare Tunnel, do **not** bind the dashboard to `0.0.0.0` just to satisfy the public hostname. Bind locally and rewrite the origin Host header:

```yaml
- hostname: dashboard.example.com
  service: http://localhost:8787
  originRequest:
    httpHostHeader: localhost:8787
```

Use a matching dashboard service command:

```ini
ExecStart=/root/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main dashboard --host 127.0.0.1 --insecure --no-open --port 8787
Restart=on-failure
RestartSec=30
```

Verification:

```bash
systemctl --user status hermes-dashboard.service --no-pager -l
systemctl status cloudflared-tunnel.service --no-pager -l
curl -sS -m 10 -o /dev/null -w 'local=%{http_code}\n' http://127.0.0.1:8787/
curl -sS -m 20 -o /dev/null -w 'external=%{http_code}\n' https://dashboard.example.com/
```

If external returns `400 Invalid Host header` while local returns `200`, cloudflared is reaching the origin but not rewriting the Host header. See `references/cloudflare-tunnel-loopback-host-header.md` for the full incident pattern.

## Pitfalls

- `API_SERVER_KEY` is mandatory -- the api_server refuses to start without it, even on loopback.
- The key goes in the environment configuration, NOT config.yaml.
- `--insecure` exposes the API keys to anyone on the network. Only use behind Tailscale or a firewall.
- Dashboard port (9119) and api_server port (8642) are different services.
- `hermes gateway restart` may time out. Use `systemctl --user restart hermes-gateway.service` instead.
- The dashboard shows ALL gateway platform statuses. "Api_server disconnected" means the platform is not running.
- **`tsc: not found`**: The monorepo workspace doesn't hoist TypeScript to `node_modules/.bin/`. Skip tsc and use `node ../node_modules/vite/bin/vite.js build` directly.
- **Dashboard process exit -15/143**: Normal when restarting. Verify new process is up with `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9119/`.
- **`hermes dashboard --stop` deletes `web_dist/`**: The `--stop` flag removes the built frontend directory. After stopping, `--skip-build` will fail. Always rebuild with vite before restarting.
- **Port 9119 (address already in use)**: After `--stop`, the TCP socket may linger in TIME_WAIT. Use `fuser -k 9119/tcp` to force-release before restarting.
- **`--skip-build` is required for dev iteration**: Without it, `hermes dashboard` runs `npm run build` which fails on `tsc: not found`. Always pass `--skip-build` after building manually with vite.
- **No `nohup`**: Hermes blocks `nohup`/`disown` wrappers. Use `subprocess.Popen` with `start_new_session=True` in Python, or `terminal(background=true)` in the agent.
- **Snapshot invalidation**: After modifying skill files via API, delete `.skills_prompt_snapshot.json` to force the system prompt to rebuild.
- **Button visibility on split screens**: Prefer footer toolbars over header buttons for action buttons (Edit/Save/Cancel). Header buttons get clipped on narrow viewports.
- **Commit messages say `hermes web`** but the actual command is `hermes dashboard`.

## Verification

After setup:

```bash
ss -tlnp | grep 8642                                  # api_server listening
hermes dashboard --status                               # dashboard running
systemctl --user status hermes-gateway.service | head 5 # gateway healthy
```
