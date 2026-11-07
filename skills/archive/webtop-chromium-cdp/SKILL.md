---
name: webtop-chromium-cdp
category: devops
description: Manage Webtop container with Chromium CDP access via s6-overlay and cron persistence. Includes container setup, CDP configuration, Singleton lock fixes, and browser access verification.
---

# Webtop Chromium CDP Management

## Container Setup

```bash
docker run -d --name webtop --restart unless-stopped \
  -p 3100:3000 \        # noVNC on 3100 (3000 often taken by Hermes)
  -p 3001:3001 \        # Selkies direct - browser access
  -e PUID=0 -e PGID=0 -e TZ=Asia/Bangkok \
  -e DISPLAY=:1 -e TITLE="Ubuntu XFCE" \
  -v <volume>:/config \
  --device /dev/dri:/dev/dri --shm-size 512mb \
  lscr.io/linuxserver/webtop:ubuntu-xfce
```

**Browser Access URLs (check Selkies FIRST):**
- **Selkies**: `https://100.91.35.121:3001/` (Tailscale IP, direct browsing, shared desktop — PREFERRED)
- noVNC: `http://<host>:3100/` (desktop view, fallback only)

## Chromium + CDP Startup Script

**Quick start from host:** `bash ~/.hermes/scripts/start-chromium-cdp.sh`

Place at `/config/custom/webtop-chromium-start.sh` (persisted via volume):

```bash
#!/bin/bash
sleep 10  # Wait for Xvfb
export DISPLAY=:1
export XDG_RUNTIME_DIR=/tmp

# CRITICAL: Clean stale locks from previous container runs
rm -f /config/.config/chromium/Singleton* 2>/dev/null
rm -rf /tmp/chromium-start-data
mkdir -p /tmp/chromium-start-data

pkill -9 -f "chromium.*remote-debugging" 2>/dev/null || true
pkill -9 -f "socat.*9223" 2>/dev/null || true
sleep 2

/usr/bin/chromium-browser \
    --no-sandbox --disable-dev-shm-usage --disable-gpu --disable-gpu-compositing \
    --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 \
    --remote-allow-origins=* --window-size=1920,1080 \
    --no-first-run --password-store=basic \
    --user-data-dir=/tmp/chromium-start-data \
    about:blank &>/dev/null &

# Wait and start socat
for i in $(seq 1 15); do
    sleep 1
    if ss -tlnp 2>/dev/null | grep -q "9222"; then
        nohup socat TCP-LISTEN:9223,fork,reuseaddr TCP:127.0.0.1:9222 &>/dev/null &
        curl -s http://127.0.0.1:9223/json/version | grep -q "Browser" && echo "CDP ready"
        exit 0
    fi
done
exit 1
```

## s6-overlay v3 Service (boot persistence)

```bash
# Create service structure
mkdir -p /etc/s6-overlay/s6-rc.d/svc-chromium

# run script
cat > /etc/s6-overlay/s6-rc.d/svc-chromium/run << 'EOF'
#!/bin/bash
exec /bin/bash /config/custom/start-chromium.sh
EOF
chmod +x /etc/s6-overlay/s6-rc.d/svc-chromium/run

# type (oneshot, not longrun)
echo "oneshot" > /etc/s6-overlay/s6-rc.d/svc-chromium/type

# dependency on Xvfb
echo "svc-xorg" > /etc/s6-overlay/s6-rc.d/svc-chromium/dependencies

# Enable service - add marker to user contents
touch /etc/s6-overlay/s6-rc.d/user/contents.d/svc-chromium
touch /etc/s6-overlay/s6-rc.d/user2/contents.d/svc-chromium
```

## Cron Fallback (restart resilience)

```bash
# Install inside container
echo "* * * * * /bin/bash /config/custom/start-chromium.sh" | crontab -
```

## CDP Testing

```bash
# From host via socat
curl http://localhost:9223/json/version

# From inside container
docker exec webtop curl http://127.0.0.1:9223/json/version

# From host via container IP
curl http://172.17.0.2:9223/json/version
```

## Related Skills

- `playwright-cdp-browser-control` — Use Playwright to interact with the Chromium CDP. Covers form filling, React apps, CAPTCHA detection, and Python automation patterns. Start Chromium CDP with `bash ~/.hermes/scripts/start-chromium-cdp.sh`.

## Pitfalls

1. **Singleton Lock + Temp Profile Tradeoff**: Chromium creates `Singleton*` lock files that persist across container recreations. Must clean them: `rm -f /config/.config/chromium/Singleton*`. 

   **CRITICAL**: The default `start-chromium.sh` uses `--user-data-dir=/tmp/chromium-start-data` (empty temp profile) which LOSES all cookies, sessions, and logged-in accounts. To access an EXISTING logged-in session (e.g., Google, Cloudflare), you MUST use the real profile `--user-data-dir=/config/.config/chromium/` instead. Only clean Singleton lock files, keep the rest:
   ```bash
   rm -f /config/.config/chromium/Singleton* /config/.config/chromium/lockfile
   DISPLAY=:1 nohup /usr/bin/chromium-browser \
     --no-sandbox --disable-dev-shm-usage --disable-gpu \
     --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 \
     --remote-allow-origins=* --no-first-run --password-store=basic \
     about:blank &>/dev/null &
   # Then socat: socat TCP-LISTEN:9223,fork,reuseaddr TCP:127.0.0.1:9222 &
   ```

   **Rule of thumb**: Temp profile = clean state (no cookies), Real profile = persistent sessions (cookies, logins).

2. **Connecting CDP to Playwright/browser tools from host**: After starting socat inside the container, you can connect from host to `http://172.17.0.2:9223` or expose port 9223 with `-p 9223:9223` and use `http://localhost:9223`. The `docker exec webtop curl http://127.0.0.1:9223/json/version` command verifies CDP is alive.

3. **aarch64 CDP Binding**: Chromium on ARM ignores `--remote-debugging-address=0.0.0.0`. It always binds 127.0.0.1. Must use socat: `socat TCP-LISTEN:9223,fork,reuseaddr TCP:127.0.0.1:9222`.

3. **WebSocket Origin**: Add `--remote-allow-origins=*` or WebSocket connections are rejected with origin mismatch.

4. **GPU in Container**: Without proper `/dev/dri` or GPU passthrough, use `--disable-gpu --disable-gpu-compositing` to avoid render crashes.

5. **s6-overlay v3 Service Registration**: Just creating `/etc/services.d/` is NOT enough. Must have:
   - Service dir in `/etc/s6-overlay/s6-rc.d/<name>/`
   - `type` file (oneshot/longrun)
   - Marker file in both `user/contents.d/` AND `user2/contents.d/`
   - Compiled database requires container restart to pick up changes
   - Cron is more reliable for in-the-moment persistence

6. **Port Conflicts**: Port 3000 is commonly used by Hermes gateway. Map noVNC to 3100 instead. Selkies on 3001 rarely conflicts.

7. **Xvfb Start Order**: Must wait ~10s for Xvfb display to be ready before launching Chromium. The startup script sleeps 10s by default.

8. **Playwright CDP Connection from Host**: To connect Playwright to webtop Chromium from the HOST machine (not inside container):
   ```python
   from playwright.sync_api import sync_playwright
   pw = sync_playwright().start()
   browser = pw.chromium.connect_over_cdp("http://172.17.0.2:9223")
   context = browser.contexts[0]  # Default context has all cookies/sessions
   page = context.pages[0] if context.pages else context.new_page()
   page.set_viewport_size({"width": 1920, "height": 1080})
   
   # IMPORTANT: Use wait_until="domcontentloaded" for SPAs
   page.goto("https://example.com", wait_until="domcontentloaded", timeout=30000)
   
   # Take screenshot
   page.screenshot(path="/tmp/screenshot.png", full_page=True)
   ```
   
   **Install**: `pip3 install playwright --break-system-packages` on host (Ubuntu 24.04).

9. **Cloudflare SPA Navigation via CDP**: Cloudflare's dashboard is a React SPA that does NOT work reliably with:
   - Direct URL navigation to sub-routes (e.g., `/onboarding`) - redirects to overview
   - `wait_until="networkidle"` often times out - use `"domcontentloaded"` instead
   
   **Alternative**: Use the Cloudflare REST API directly with a token that has `Zone.Zone.Read` + `Zone.DNS.Edit` permissions. The token from `~/.hermes/mcp/mcporter.json` often has limited scopes (Account + Tunnel only). For full DNS management, create a token with `Edit zone DNS` template at dash.cloudflare.com > Profile > API Tokens.

10. **Hostinger vs Cloudflare sessions are separate**: The webtop may have Google sessions for Cloudflare but NOT for Hostinger. If Hostinger uses a different login (email/password login, not Google SSO), the session won't be pre-connected. Verify login status via screenshot before assuming credentials are available.

11. **Empty svc-chromium breaks ALL s6 services**: If `/etc/s6-overlay/s6-rc.d/svc-chromium/` exists but is EMPTY (no `type`, no `run`, no `dependencies.d`), s6-overlay fails at boot and prevents ALL other services (selkies, nginx, dbus, xorg) from starting. Fix:
    ```bash
    # Create proper service definition
    echo "longrun" > /etc/s6-overlay/s6-rc.d/svc-chromium/type
    mkdir -p /etc/s6-overlay/s6-rc.d/svc-chromium/dependencies.d
    touch /etc/s6-overlay/s6-rc.d/svc-chromium/dependencies.d/svc-xorg
    cat > /etc/s6-overlay/s6-rc.d/svc-chromium/run << 'RUNEOF'
    #!/command/execlineb -P
    /usr/bin/chromium-browser --no-sandbox --disable-dev-shm-usage --disable-gpu --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-google-profile --no-first-run --no-default-browser-check
    RUNEOF
    chmod +x /etc/s6-overlay/s6-rc.d/svc-chromium/run
    docker restart webtop
    ```
    **Verification**: After restart, check `docker exec webtop ps aux | grep selkies` — if empty, svc-chromium is still broken.