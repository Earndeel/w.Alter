---
name: anti-bot-navigation
description: "Master navigation stack — decision tree for anti-bot bypass. Routes to Camoufox (host), Brave Mac (CDP), or Webtop Chromium based on site protection level. Includes behavioral simulation, CAPTCHA auto-solve, and cookie injection."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [browser, anti-bot, navigation, stealth, captcha, scraping]
    related_skills: [webtop-authenticated-browsing, mac-brave-walter, hermes-camoufox-setup, recaptcha-v2-bypass, scrapling]
---

# Anti-Bot Navigation Stack

Complete decision tree and toolkit for browsing/scraping any site, from basic to ultra-strict protection.

## Architecture Overview

```
                    ┌─────────────────────────────────────────┐
                    │           W.Alter Navigation             │
                    └──────────────┬──────────────────────────┘
                                   │
              ┌────────────────────┼─────────────────────┐
              │                    │                     │
     ┌────────▼────────┐  ┌───────▼────────┐  ┌────────▼────────┐
     │  Camoufox Host   │  │ Brave Mac CDP  │  │ Webtop Chromium  │
     │  (Xvraf :116)    │  │ (port 9226)    │  │ (172.17.0.3:9223)│
     │  Port 9377       │  │ via SSH tunnel │  │ via socat 9223   │
     │                  │  │                │  │                  │
     │  95% of sites    │  │ DataDome/CF    │  │ Fallback/visual  │
     │  Linux spoof     │  │ Real macOS     │  │ Visible browsing │
     └──────────────────┘  └────────────────┘  └──────────────────┘
              │                    │                     │
              └────────────────────┼─────────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │     Behavioral Simulation        │
                    │     human_sim.py + captcha_      │
                    │     solver.py                    │
                    └─────────────────────────────────┘
```

## Decision Tree

```
Need to browse/scrape a site?
│
├─ Is it a simple site (no anti-bot)?
│   └─ Camoufox host (Xvraf) + human_sim
│       └─ API: POST /tabs → navigate → screenshot → click
│
├─ Is it Cloudflare-protected (medium)?
│   └─ Camoufox host + Scrapling solve_cloudflare=True
│       └─ Fallback: wait for Turnstile auto-resolve
│
├─ Is it DataDome / Cloudflare strict / hCaptcha?
│   └─ Brave Mac CDP (port 9226) + human_sim + captcha_solver
│       └─ Real macOS fingerprint, real GPU, real fonts
│       └─ Auto-solve: reCAPTCHA audio + Groq Whisper
│       └─ Manual fallback: user solves in 2 seconds
│
├─ Google Lens / Google strict anti-bot?
│   └─ Webtop Camoufox non-headless (port 9378 in container)
│       └─ Visible via Selkies (https://100.91.35.121:3001)
│       └─ Google homepage works, but Lens still returns 403
│       └─ For reverse image: use Yandex instead (see camoufox-social-scrape)
│
├─ Do you need the user to see what's happening?
│   └─ Webtop Chromium (172.17.0.3:9223) + visible
│       OR Camoufox non-headless in Webtop (port 9378, visible via Selkies)
│
└─ Is it Facebook / Google strict?
    └─ Extract cookies from Mac Brave SQLite (see camoufox-social-scrape)
        └─ Inject into Camoufox host for authenticated browsing
        └─ NEVER connect Scrapling/Playwright to Mac Brave CDP (opens visible tabs)
```

## Protection Level Quick Reference

| Level | Examples | Engine | human_sim | CAPTCHA solve |
|---|---|---|---|---|
| **None** | Most SaaS, docs, blogs | Camoufox host | Optional | N/A |
| **Low** | Basic rate limiting | Camoufox host | ✅ scroll+click | N/A |
| **Medium** | Cloudflare Turnstile | Camoufox host | ✅ | auto-resolve |
| **High** | DataDome, hCaptcha | Brave Mac CDP | ✅ mandatory | audio+Whisper |
| **Ultra** | Cloudflare JS challenge strict | Brave Mac CDP | ✅ mandatory | manual fallback |
| **Impossible** | Google Lens | N/A | N/A | BLOCKED (403). Use Yandex. |

## Modules

### human_sim.py (`~/.hermes/scripts/human_sim.py`)

Human-like browser interactions via Playwright CDP:

```python
from human_sim import HumanSimulator
sim = HumanSimulator(page)

# Before first interaction — random mouse noise
sim.random_mouse_noise()

# Scroll and click with human behavior
sim.scroll_and_click('button.submit')

# Type with variable speed, occasional typos
sim.type_text('input[name="email"]', 'user@example.com')

# Idle browsing (scroll, move, pause)
sim.idle_browse(5.0)
```

Key features:
- Bezier curve mouse trajectories with jitter
- Log-normal pause distribution (realistic timing)
- Occasional typos with correction (2% rate)
- Scroll overshoot and correction
- Variable typing speed per character
- Thinking pauses (5% chance per keystroke)

### captcha_solver.py (`~/.hermes/scripts/captcha_solver.py`)

Auto-solve CAPTCHAs with multiple fallback strategies:

```python
from captcha_solver import CaptchaSolver
solver = CaptchaSolver(page, groq_api_key="gsk_...")

# Detect what's on the page
challenge = await solver.detect_challenge()  # 'none', 'recaptcha_invisible', etc.

# Auto-solve anything
solved = await solver.auto_solve()

# Specific reCAPTCHA solve
token = await solver.solve_recaptcha(site_key="6Ldx...")
```

Solve priority:
1. `grecaptcha.execute()` — invisible reCAPTCHA, instant, no interaction
2. Audio challenge + Groq Whisper — checkbox reCAPTCHA
3. 2Captcha API — paid fallback (key from vault)
4. **Telegram SOS** — screenshot + clickable Webtop link sent to user
5. `wait_for_manual_solve()` — polls until user resolves the challenge

## Cookie Pipeline

### From Mac Brave → Any Engine

```python
# 1. Extract from Mac Brave (CDP 9222 via SSH tunnel)
#    → /tmp/brave-cookies-all.json

# 2. Filter per-domain
google_cookies = [c for c in all_cookies if "google" in c["domain"]]

# 3. Inject into chosen engine:
#    Camoufox:  POST /sessions/walter/cookies
#    Brave Mac: context.add_cookies() via CDP 9226
#    Webtop:    context.add_cookies() via CDP 9223
```

### Cookie-Fingerprint Consistency

⚠️ **Critical**: Cookies from Mac Brave should go to Mac Brave CDP (same fingerprint).
Camoufox (Linux) with Mac cookies = fingerprint mismatch = risk on strict sites.

| Cookie Source | Best Engine | Why |
|---|---|---|
| Mac Brave | Brave Mac CDP | Same OS, same fingerprint |
| Mac Brave | Camoufox host | OK for non-strict sites |
| No auth needed | Camoufox host | No cookie mismatch possible |

## Interaction Patterns

### Pattern 1: Safe Navigation (Most Sites)

```python
# Camoufox host — no user impact
from human_sim import HumanSimulator

# Via Camoufox HTTP API
conn = http.client.HTTPConnection("localhost", 9377)

# Create tab
cf("POST", "/tabs", {"userId": "walter", "sessionKey": "task", "url": url})

# Wait for load, screenshot
time.sleep(5)
screenshot = cf_get(f"/tabs/{tab_id}/screenshot")

# Get snapshot for refs
snap = cf_get(f"/tabs/{tab_id}/snapshot")

# Human-like interaction
sim = HumanSimulator(page)  # if using Playwright directly
sim.scroll_and_click('[e38]')
```

### Pattern 2: Anti-Bot Navigation (Strict Sites)

```python
# Brave Mac CDP — real fingerprint
from playwright.sync_api import sync_playwright
from human_sim import HumanSimulator
from captcha_solver import CaptchaSolver

pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9226")  # via SSH tunnel
context = browser.contexts[0]
context.add_cookies(mac_cookies)
page = context.new_page()

sim = HumanSimulator(page)
solver = CaptchaSolver(page, groq_api_key=groq_key)

# Navigate with human behavior
page.goto(url, wait_until="domcontentloaded")
sim.random_mouse_noise()
sim.idle_browse(3.0)

# Auto-solve any challenge
await solver.auto_solve()

# Interact with behavioral sim
sim.scroll_and_click('selector')
sim.type_text('input', 'text')
```

### Pattern 3: Visible Browsing (User Supervision)

```python
# Webtop Chromium — user sees everything on noVNC
browser = pw.chromium.connect_over_cdp("http://172.17.0.3:9223")
context = browser.contexts[0]
context.add_cookies(cookies)
page = context.new_page()
page.goto(url)
# User can take over at any time
```

### Pattern 4: Telegram SOS Fallback (Last Resort)

When all auto-solve fails, send user a 1-click link via Telegram:

```python
from captcha_solver import CaptchaSolver
solver = CaptchaSolver(page, groq_api_key="gsk_...")

# Auto-solve attempt
solved = await solver.auto_solve()

if not solved:
    # Telegram SOS already sent automatically by auto_solve()
    # Now wait for user to solve manually
    solved = await solver.wait_for_manual_solve(timeout=120)
    
    if solved:
        # Continue navigation
        pass
    else:
        # User didn't respond — abort or retry
        pass
```

**Telegram SOS flow:**
1. Screenshot taken automatically
2. Message sent with Webtop HTTPS link (`https://100.91.35.121:3001`)
3. User clicks link → Webtop opens with the challenge visible
4. User solves challenge in the browser
5. Agent detects challenge disappears → continues

The Telegram message includes:
- Challenge type (reCAPTCHA, DataDome, hCaptcha, Cloudflare)
- Page URL
- Clickable Webtop link
- Screenshot of the challenge

## SSH Tunnels Required

| Tunnel | From | To | Purpose |
|---|---|---|---|
| `ssh -L 9222:localhost:9222 Mac` | VPS | Mac | Main Brave cookie extraction |
| `ssh -L 9226:localhost:9226 Mac` | VPS | Mac | W.Alter Brave CDP control |
| Tailscale exit node | VPS → Mac → Internet | Mac IP | IP routing |

## Pitfalls

1. **⚠️ NEVER connect Scrapling/Playwright to Mac Brave CDP without permission**: Opening tabs via CDP creates visible pop-ups and new tabs on Monsieur's Mac, disrupting his work. This is a HARD RULE — no exceptions. If you need authenticated browsing, extract cookies from Brave's SQLite DB and inject into Camoufox instead. See `camoufox-social-scrape` skill → references/brave-cookie-extraction.md.
2. **Port 9226 ≠ cookies**: Port 9226 is the W.Alter Brave instance (`--user-data-dir=/tmp/brave-walter`) — it has NO social media cookies. The main Brave (with Facebook/Instagram/LinkedIn cookies) has NO remote debugging enabled. Cookie extraction from SQLite is the only path.
2. **reCAPTCHA token expiry**: Tokens valid ~2 minutes. Generate right before use.
3. **Audio challenge selectors**: Chrome 147+ changed reCAPTCHA selectors. Screenshot iframe to inspect if broken.
4. **Turnstile auto-resolve**: Works most times with real browser. If stuck >30s, manual needed.
5. **Mac sleep**: SSH tunnels die. Re-run `mac-brave-walter.sh` after wake.
6. **human_sim on Camoufox API**: HumanSimulator needs Playwright page object. For Camoufox HTTP API, implement timing delays manually.
7. **Rate limiting**: Even with stealth, too-fast requests trigger rate limits. Use `human_pause()` between actions.

## Scripts

| Script | Path | Purpose |
|---|---|---|
| `human_sim.py` | `~/.hermes/scripts/` | Behavioral simulation module |
| `captcha_solver.py` | `~/.hermes/scripts/` | CAPTCHA auto-solver module |
| `mac-brave-walter.sh` | `~/.hermes/scripts/` | Launch + tunnel Brave Mac instance |

## Verification Checklist

- [ ] Camoufox running: `curl http://localhost:9377/health`
- [ ] Brave Mac running: `curl http://localhost:9226/json/version` (via tunnel)
- [ ] Tailscale exit node: `curl ifconfig.me` should show Mac's IP
- [ ] human_sim importable: `python3 -c "from human_sim import HumanSimulator"`
- [ ] captcha_solver importable: `python3 -c "from captcha_solver import CaptchaSolver"`
- [ ] Groq key available: `vault get groq` or env GROQ_API_KEY
- [ ] 2Captcha key (optional): `vault get 2captcha`
