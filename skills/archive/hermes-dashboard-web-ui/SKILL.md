---
name: hermes-dashboard-web-ui
description: "Hermes web dashboard and desktop app setup, access, and troubleshooting. Use when the user asks about the Hermes web UI, dashboard, desktop app, or browser-based admin panel."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [hermes, dashboard, web-ui, desktop, admin]
    related_skills: [hermes-agent, hermes-agent-update, ssh-mac-remote-control]
---

# Hermes Web Dashboard & Desktop Apps

## When to Use

- User asks about the Hermes web UI, dashboard, or browser-based admin panel
- User wants to manage Hermes from a browser instead of CLI
- User downloaded the Hermes DMG and can't install it
- User asks about Hermes Desktop app vs CLI

## Quick Start — Web Dashboard

```bash
hermes dashboard              # launch on port 9119, auto-opens browser
hermes dashboard --port 8080  # custom port
hermes dashboard --host 0.0.0.0 --insecure  # expose on network
hermes dashboard --status     # check if running
hermes dashboard --stop       # stop
hermes dashboard --no-open    # don't auto-open browser
```

FastAPI + Vite/React admin panel. Pages: Status, Config editor, API Keys, Sessions, Skills, Cron, Logs, Analytics, MCP Catalog.

Docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard

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

## Identifying Which App

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

## Remote Access (from Mac to VPS)

```bash
# Via Tailscale SSH tunnel
ssh -tt walter-ts "hermes dashboard --port 9119 --no-open"
# Then access at http://localhost:9119 via SSH port forwarding

# Or expose directly (behind Tailscale only)
hermes dashboard --host 0.0.0.0 --insecure --port 9119
```

## Dashboard Development — Adding Features

The dashboard is a **FastAPI backend** (`hermes_cli/web_server.py`) + **Vite/React frontend** (`web/src/`).

### Architecture

```
hermes-agent/
├── hermes_cli/web_server.py     # FastAPI app — all /api/* routes
├── web/src/
│   ├── lib/api.ts               # Frontend API client (fetchJSON wrappers)
│   ├── pages/*.tsx               # Page components (SkillsPage, etc.)
│   └── App.tsx                   # Route registry
├── hermes_cli/web_dist/         # Built frontend (served by FastAPI)
└── web/node_modules/            # Frontend deps
```

### Adding an API Endpoint

1. Add route in `hermes_cli/web_server.py` near the related existing endpoints:

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

2. Auth: endpoints behind `/api/*` require the session token as `Authorization: Bearer <token>`. The token is injected into the HTML as `window.__HERMES_SESSION_TOKEN__`.

### Adding a Frontend API Method

In `web/src/lib/api.ts`, add to the `api` object:

```typescript
getSkillContent: (name: string) =>
  fetchJSON<{ success: boolean; content: string }>(
    `/api/skills/${encodeURIComponent(name)}/content`,
  ),
```

### Adding a Page Component

In `web/src/pages/YourPage.tsx`, register in `App.tsx`:

```typescript
import YourPage from "@/pages/YourPage";
// In the routes object:
"/your-route": YourPage,
```

### Build & Deploy

```bash
cd /root/.hermes/hermes-agent/web
node ../node_modules/vite/bin/vite.js build    # outputs to hermes_cli/web_dist/
hermes dashboard --stop                         # restart to pick up backend changes
hermes dashboard --host 0.0.0.0 --insecure --no-open --port 9119 --skip-build
```

Frontend changes need a vite build. Backend changes need a dashboard restart.

**Critical build pitfalls:**

- **`npm run build` fails** — runs `tsc -b && vite build` but `tsc` is often missing from the monorepo workspace. Use `node ../node_modules/vite/bin/vite.js build` directly from `web/` to skip type-checking.
- **`vite build` detected as long-lived process** — the terminal tool's heuristics flag vite as a server. Use `node ../node_modules/vite/bin/vite.js build` (not the shell wrapper) to avoid this.
- **`hermes dashboard --stop` deletes `web_dist/`** — the stop command cleans the build output. Always rebuild before restarting, or use `--skip-build` after a manual build.
- **`--skip-build` requires `web_dist/index.html`** — if missing, the dashboard refuses to start. Build first, then `--skip-build`.
- **Exit code -15 from `--stop`** — SIGTERM is expected. Terminal tool treats it as failure; use `execute_code` with `subprocess.run()` to avoid false error loops.
- **Port release delay** — after stopping, add `sleep 2` before restarting to let the port fully release.

### Testing API Endpoints

```python
import requests, re
r = requests.get("http://127.0.0.1:9119/skills")
token = re.search(r'__HERMES_SESSION_TOKEN__="([^"]+)"', r.text).group(1)
headers = {"Authorization": f"Bearer {token}"}
requests.get("http://127.0.0.1:9119/api/skills", headers=headers)
```

### Pitfalls

- **DMG is just an installer**, not the app. Skip it and run the install script directly.
- **Intel Macs can't run the Tauri DMG** (arm64-only). Use the Electron desktop app or the CLI.
- **`--insecure` exposes API keys** to anyone on the network. Only use behind Tailscale or trusted LAN.
- **`hermes dashboard` replaces both native apps** for most use cases — no need for the desktop app if you have browser access.
- **Commit messages say `hermes web`** but the actual command is `hermes dashboard`.

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

### Theme palette pitfalls

- **`warmGlow` adds a color tint** over the entire background. Even `rgba(3, 223, 232, 0.15)` at 15% alpha is visible. Use `rgba(0, 0, 0, 0)` for a pure flat background.
- **`noiseOpacity > 0` adds grain texture**. Set to 0 for a clean look.
- **`midground` drives everything** — primary, accent, border, card, muted, ring are all derived from it via `color-mix()`. A bright midground on a dark background will tint cards, borders, and muted areas.
- **`colorOverrides` escape hatch** — when the derived colors don't look right, pin specific shadcn tokens here (e.g. `card`, `border`, `muted`).
- **CSS derivation** lives in `web/src/index.css` — look for `--color-card`, `--color-muted`, `--color-border` to understand how palette maps to UI.
