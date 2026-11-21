---
name: google-auth-novnc
category: devops
description: Set up persistent Google login via noVNC browser for automated OAuth flows. User logs in ONCE, then all future "Continue with Google" buttons are automatic.
---

## Trigger
When a service requires Google OAuth and user wants fully automated login.

## Architecture
PREFER: Selkies desktop (already running at `https://100.91.35.121:3001/` via Tailscale). Just launch Chromium there.
FALLBACK: Xvfb (:99) → Chromium (persistent profile) → x11vnc (:5900) → noVNC (:6080) → Cloudflare Tunnel

## Steps (Selkies — preferred)
```bash
# Launch Chromium on the existing Selkies desktop (DISPLAY=:1, NOT :0)
DISPLAY=:1 chromium-browser --no-sandbox --disable-dev-shm-usage --user-data-dir=/tmp/chrome-google-profile https://accounts.google.com/signin &
```
Lucas accesses via `https://100.91.35.121:3001/` (Tailscale). No tunnel needed.

## Steps (Fallback — noVNC)
```bash
Xvfb :99 -screen 0 1920x1080x24 &
DISPLAY=:99 chromium-browser --no-sandbox --disable-dev-shm-usage --disable-gpu \
  --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-google-profile \
  --no-first-run --no-default-browser-check --window-size=1920,1080 \
  https://accounts.google.com/signin &
x11vnc -display :99 -forever -nopw -rfbport 5900 &
/usr/share/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 &
```

## Pitfalls
- **Snap Chromium AppArmor**: Cannot write to `~/.hermes/`. Use `/tmp/chrome-google-profile`.
- **Snap private tmp**: Snap remaps `/tmp/` to `/tmp/snap-private-tmp/snap.chromium/tmp/`. When reading cookies programmatically (sqlite3), use the remapped path.
- **CF quick tunnel + named tunnel conflict**: Use `cloudflared --config /dev/null tunnel --url ...` to avoid inheriting named tunnel config (causes 404).
- **SingletonLock**: `rm -f /tmp/snap-private-tmp/snap.chromium/tmp/chrome-google-profile/SingletonLock` if Chromium crashes.
- **Google OAuth via Playwright CDP**: After Google login, connect via `pw.chromium.connect_over_cdp("http://localhost:9222")` to reuse the authenticated session.
- **Vast.ai API key creation**: Endpoint is `POST /api/v0/auth/apikeys/` with `{"name": "..."}` on `cloud.vast.ai` (not `console.vast.ai`). Must be called from authenticated Playwright page context. Full key only shown once in response.
- **Stripe checkout automation**: Separate skill — see `stripe-checkout-automation`.
- **Bitwarden item creation**: Requires base64-encoded JSON piped via stdin, not inline JSON string.
- **Vault add syntax**: `vault add service field value` (space-separated, not slash).
- **Selkies display**: DISPLAY=:1 (NOT :0). Xvfb runs on :1 with 15360x8640 resolution.
- **Container Chromium CDP**: Listens on `127.0.0.1:9222` inside container — NOT accessible from host. Use `docker exec webtop curl http://127.0.0.1:9222/json/list` to interact, or use the host Chromium on port 9222 (separate instance).
- **Two Chromium instances**: Host has its own Chromium on port 9222 (persistent profile). Container has another on 127.0.0.1:9222 (Selkies display). They are independent.
- **svc-chromium broken in webtop**: If s6-overlay fails at boot with `svc-chromium/type: No such file`, the service directory is empty. Fix: create `type` (echo "longrun"), `run` script, and `dependencies.d/` inside the container, then restart. See `references/webtop-s6-fix.md`.
- **Google 2FA blocks NEW OAuth clients**: Persistent session works for direct Google services (Gmail, account.google.com) but Google REQUIRES 2FA push notification for EVERY NEW OAuth client (Kaggle, Modal, GitHub, etc.). Cannot be automated — user must approve on phone ONCE per service. After that, API keys bypass OAuth. Beeper intercepts SMS codes but NOT Google Prompts (push 2FA).
- **Stripe checkout automation**: See `stripe-checkout-automation` skill. Stripe iframes are PCI-secured and resist programmatic card entry.
- **Automation-first mindset**: Always check for existing infrastructure (Selkies, CDP) before building new stacks.

## After Login
Any Playwright CDP connection on `localhost:9222` inherits the Google session. "Continue with Google" auto-approves.

## Infrastructure Reference
- **Selkies desktop**: `https://100.91.35.121:3001/` (Tailscale IP, port 3001)
- **Chromium CDP**: port 9222, persistent profile `/tmp/chrome-google-profile`
- **Webtop container**: Docker `webtop`, Selkies+nginx+s6-overlay
- **Selkies port**: 3001 inside container → 3001 on host (mapped via Docker)

## Verify
```bash
curl -sI "https://TUNNEL_URL/vnc_lite.html" | head -3
```

## Telegram Notification
```bash
curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  -d "text=🖥️ Browser: https://URL/vnc.html"
```
