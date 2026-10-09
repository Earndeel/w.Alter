---
name: mac-brave-walter
description: "Separate Brave instance on Mac for anti-detect browsing — dedicated profile, CDP on port 9226, SSH tunnel to VPS. For DataDome/Cloudflare sites that need real macOS fingerprint."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [browser, cdp, anti-detect, mac, brave, fingerprint]
    related_skills: [webtop-authenticated-browsing, playwright-cdp-browser-control]
---

# Mac Brave W.Alter Instance

A separate Brave browser instance on the Mac with its own profile, for sites requiring a real macOS fingerprint (DataDome, Cloudflare strict, etc.). Does NOT interfere with the user's main Brave.

## Architecture

```
VPS (localhost:9226) ──SSH tunnel──→ Mac (localhost:9226) ──→ Brave W.Alter
                                              Profile: /tmp/brave-walter
```

## When to Use

- **NOT the default** — prefer Camoufox + auth-only cookies first (faster, no SSH tunnel needed). See `webtop-authenticated-browsing` skill.
- Sites with DataDome (Tinder, etc.) that specifically need real macOS fingerprint
- Cloudflare strict challenges that Camoufox can't solve
- When Camoufox fingerprint (Linux-based) would mismatch Mac cookies
- When user needs to SEE the browser on their Mac screen

## Quick Start

```bash
# Launch + tunnel (idempotent)
bash ~/.hermes/scripts/mac-brave-walter.sh [url]

# Or via Playwright CDP from Python
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9226")
context = browser.contexts[0]
# Inject cookies from Mac main Brave if needed
context.add_cookies(cookies)
page = context.new_page()
page.goto("https://target-site.com")
```

## Key Details

| Item | Value |
|---|---|
| Mac host | `lucasjouvencon@100.127.150.1` |
| CDP port (Mac) | 9226 |
| CDP port (VPS tunnel) | 9226 |
| Profile | `/tmp/brave-walter` |
| Browser | Chrome/148 (Brave) |
| User-Agent | Real macOS UA, not spoofed |

## Stealth Level

- ✅ Real macOS fingerprint (canvas, WebGL, fonts, GPU, audio)
- ✅ Real IP (via Tailscale exit node)
- ✅ Real Brave browser (not headless, not spoofed)
- ✅ Persistent profile (cookies, localStorage survive restarts)
- ✅ Separate from user's main Brave (no disruption)

## Cookie Injection

The separate instance has its own profile (`/tmp/brave-walter`). For sites where the user is logged in on their main Brave, follow the full extraction pipeline in `webtop-authenticated-browsing` skill → "Step 1: Extract Cookies from Mac Brave".

### Key constraint: Main Brave has NO CDP by default

The main Brave (user's daily browser, PID 478, profile `~/Library/Application Support/BraveSoftware/Brave-Browser/`) is launched without `--remote-debugging-port`. **Port 9222 is not available.** The only CDP port is 9226 (the walter instance).

### Cookie extraction order of preference

1. **Keychain decryption** (requires `macos/brave_keychain_key` in vault — see `webtop-authenticated-browsing` skill): copy SQLite Cookies DB → decrypt with AES-128-CBC → inject into walter Brave via `context.add_cookies()`. **Fully automated once key is in vault.**
2. **Login with stored credentials**: if creds are in vault, navigate to login page via walter Brave CDP, fill form, save fresh cookies. Works for sites without MFA.
3. **Ask user for Keychain key** (one-time): `security find-generic-password -s "Brave Safe Storage" -a "Brave" -w` run locally in Terminal.app. Store result in vault as `macos/brave_keychain_key`. This unlocks option 1 permanently.

### What NOT to do

- **Do NOT restart main Brave** with `--remote-debugging-port` — user has explicitly refused this approach.
- **Do NOT connect Scrapling/Playwright to main Mac Brave** — it creates visible tabs on the user's screen (disturbing).
- **Do NOT try osascript `find-generic-password` via SSH** — macOS Keychain ACL blocks non-interactive access even with admin privileges (error 36). Tested 2026-05-24: `set-key-partition-list` does NOT fix the ACL. The `osascript ... with administrator privileges` approach documented in `webtop-authenticated-browsing` is unreliable (~30% success). **Ask user to run locally** — it's a 10-second one-time task. Store result in vault as `macos/brave_keychain_key`.

## Brave-in-Webtop (Container Fallback)

When Mac is unavailable or Camoufox fails on a site, use Brave inside the webtop container as a fallback browser. Same cookie injection pattern via Playwright CDP.

**When Camoufox SPA fails**: Some SPAs (Bumble, etc.) load JS files but never execute in Camoufox. Switch to Brave-in-webtop immediately. See `web-service-browser` skill for the full fallback pattern.

## Anti-Bot Integration

### Behavioral Simulation (mandatory for strict sites)

```python
import sys
sys.path.insert(0, "/root/.hermes/scripts")
from human_sim import HumanSimulator

sim = HumanSimulator(page)  # Playwright page via CDP 9226

# On page load: random mouse noise before any interaction
sim.random_mouse_noise()
sim.idle_browse(3.0)

# Click with human behavior
sim.scroll_and_click('selector')

# Type with variable speed + occasional typos
sim.type_text('input[name="q"]', 'search query')
```

### CAPTCHA Auto-Solve

```python
from captcha_solver import CaptchaSolver

solver = CaptchaSolver(page, groq_api_key="gsk_...")

# Auto-detect and solve
challenge = await solver.detect_challenge()
if challenge != 'none':
    solved = await solver.auto_solve()
    if not solved:
        print("Manual solve needed — user can solve in Brave window")
```

### DataDome Specific

DataDome checks behavioral biometrics. Mandatory steps:
1. `sim.random_mouse_noise()` on page load
2. `sim.scroll()` before any click
3. `sim.human_pause()` between actions (0.5-2s)
4. Never click without scrolling into view first
5. If DataDome challenge iframe appears: user solves manually in Brave window

### Full Example: Browse a DataDome-protected site

```python
import asyncio, sys
sys.path.insert(0, "/root/.hermes/scripts")
from human_sim import HumanSimulator
from captcha_solver import CaptchaSolver
from playwright.async_api import async_playwright

async def browse_protected(url):
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://localhost:9226")
    context = browser.contexts[0]
    page = await context.new_page()
    
    sim = HumanSimulator(page)
    solver = CaptchaSolver(page, groq_api_key="gsk_...")
    
    await page.goto(url, wait_until="domcontentloaded")
    sim.random_mouse_noise()
    sim.idle_browse(3.0)
    
    # Auto-solve any challenge
    await solver.auto_solve()
    
    # Now interact with human behavior
    sim.scroll_and_click('a.product')
    sim.human_pause()
    # ...
```

## Pitfalls

1. **Port conflict**: If user's main Brave uses 9222, don't use the same port. W.Alter uses 9226.
2. **SSH tunnel dies**: If Mac sleeps, tunnel drops. Re-run `mac-brave-walter.sh` to reconnect. See `references/brave-walter-relaunch.md` for full recovery procedure.
3. **Profile cleanup**: `/tmp/brave-walter` persists across Mac restarts but `/tmp` may be cleaned. For persistence, use `~/.brave-walter/` instead.
4. **Two Brave instances**: Both can run simultaneously. Main Brave is unaffected.
5. **Focus stealing**: New tabs may appear in the W.Alter Brave. Minimize it or put on a different desktop space.
6. **Brave walter crashes**: The instance can die when CDP connections drop. See `references/brave-walter-relaunch.md` for relaunch procedure. Use full binary path, NOT `open -a`.
7. **Downloads go to Mac, not VPS**: `download.save_as()` via CDP creates empty files on VPS. Intercept URL with `expect_download()`, then `curl` on VPS.

## Verification

```bash
# Check tunnel
curl -s http://localhost:9226/json/version

# List tabs
curl -s http://localhost:9226/json/list

# Check user-agent (should be real macOS)
curl -s http://localhost:9226/json/version | jq .UserAgent
```
