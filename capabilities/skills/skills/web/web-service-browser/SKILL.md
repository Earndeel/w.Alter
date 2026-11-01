---
name: web-service-browser
description: "One-shot browser access to web services (Gemini, Suno, Grok, etc.) via Mac Brave cookies → Camoufox injection. Fast extract-decrypt-inject-navigate pipeline."
version: 1.0.0
author: W.Alter
triggers:
  - open gemini
  - open suno
  - open grok
  - use gemini web
  - use suno web
  - browser service
  - web interface
  - cookies inject
  - mon twitter
  - mon compte
  - check my twitter
  - checker mon twitter
  - ouvre gemini
  - ouvre suno
  - ouvre grok
  - connecte-toi
  - annule abonnement
  - cancel subscription
  - cancel plan
  - remboursement
  - refund
  - hailuo
  - anthropic
  - désabonner
metadata:
  hermes:
    tags: [browser, cookies, camoufox, webtop, gemini, suno, grok, services]
related_skills: [camoufox-social-scrape, webtop-authenticated-browsing]
---

# Web Service Browser — Fast Pipeline

> **State on 2026-11-01.** To act as Monsieur on a site, the normal path is `walter_browse` (Hermes) or `browser_session` + `walter-browser` (Claude Code, Codex, DSH): his cookies are injected server-side and the agent only gets metadata. Never extract Brave cookies, keychain keys or LevelDB yourself; the extraction steps below are history and debugging material. Entry: `walter-browse-orchestrator`.

One-shot: extract cookies from Mac Brave → decrypt → inject into Camoufox → navigate to service.
Use the web interfaces directly instead of paying for API calls.

> **Current Camoufox-Max API (verified 2026-07-10):** the active server on host port `9377` is `/root/.hermes/camoufox-max/server-max.js` and uses singular routes: `POST /session/cookies`, `POST /tab/new`, `POST /tab/navigate`, `POST /tab/snapshot`, `POST /tab/screenshot`, `POST /tab/click`, `POST /tab/type`, `POST /tab/evaluate`, and `POST /tab/close`. Legacy `/tabs` and `/sessions/...` routes return `404`; do not copy those older examples into new scripts. Webtop Camoufox on `9378` must be checked separately before use.

**Related skills**: `camoufox-social-scrape` (X/Twitter deep scraping, OSINT), `webtop-authenticated-browsing` (full reference for cookie extraction, Camoufox API, anti-bot patterns).
Use the web interfaces directly instead of paying for API calls.

## Snapshot vs Screenshot (for user explanation)

| | Snapshot | Screenshot |
|---|---|---|
| **Format** | Text structured (DOM tree) | PNG image |
| **Content** | Every element = name, text, clickable refs | What you'd see on screen |
| **Use case** | Data extraction, parsing, automation | Visual verification |
| **Size** | ~15-30K chars text | ~200-600KB image |
| **API call** | `GET /tabs/:id/snapshot` | `GET /tabs/:id/screenshot` |

Snapshot example:
```
article "The Figen @TheFigen_ Il y a 13h Les manchots sont programmés...
83 réponses, 669 reposts, 8140 J'aime, 264806 vues"
```

**For scraping**: snapshot is the primary tool. Screenshot is for visual verification only.

## Architecture

```
Mac Brave (no CDP) → SSH sqlite3 → decrypt (vault key) → Camoufox webtop (9378) → interact
```

**Camoufox runs in webtop container ONLY** — host path is unreliable.
**Viewport: 1920×1080** — patched in server.js at first run.

## Parallel Multi-Service Opening (PREFERRED)

Extract cookies ONCE on host, split by domain, inject into multiple tabs concurrently.
This is 3-5× faster than running ws-browser.py sequentially.

```bash
# 1. Extract ALL service cookies in one SSH call
ssh lucasjouvencon@100.127.150.1 "sqlite3 /tmp/brave-cookies-latest.db \
  \"SELECT ... WHERE host_key LIKE '%google%' OR host_key LIKE '%suno%' OR host_key LIKE '%grok%'\"" > /tmp/all-raw-cookies.txt

# 2. Decrypt + split on HOST (vault + pycryptodome available here, NOT in webtop)
python3 /tmp/split-cookies.py  # -> /tmp/cookies-{gemini,suno,grok}.json

# 3. Push into container
docker cp /tmp/cookies-*.json webtop:/tmp/

# 4. Parallel inject + navigate (ThreadPoolExecutor, 3 workers)
docker exec webtop python3 -c "..."  # see scripts/parallel-open.py
```

**Result: 3 services in ~8s** vs ~45s sequential.

## Tab Lifecycle (IMPORTANT — RAM management)

```python
# Close single tab
conn.request('DELETE', f'/tabs/{tab_id}?userId=walter')

# Close all tabs
conn.request('GET', '/tabs?userId=walter')
tabs = json.loads(conn.getresponse().read().decode())
for t in tabs.get('tabs', []):
    conn.request('DELETE', f'/tabs/{t["tabId"]}?userId=walter')
    conn.getresponse().read()
```

**Pattern**: open → interact → screenshot/extract → close. Never leave tabs open between tasks.

## Quick Commands (after script runs)

```bash
# Screenshot
docker exec webtop python3 -c "
import http.client
conn = http.client.HTTPConnection('localhost', 9378)
conn.request('GET', '/tabs/TAB_ID/screenshot?userId=walter&sessionKey=SESSION_KEY')
with open('/tmp/svc-screenshot.png','wb') as f: f.write(conn.getresponse().read())
"

# Snapshot (find elements)
docker exec webtop python3 -c "
import http.client, json
conn = http.client.HTTPConnection('localhost', 9378)
conn.request('GET', '/tabs/TAB_ID/snapshot?userId=walter&sessionKey=SESSION_KEY')
print(json.loads(conn.getresponse().read().decode())['snapshot'][:3000])
"

# Type into element
docker exec webtop python3 -c "
import http.client, json
conn = http.client.HTTPConnection('localhost', 9378)
body = json.dumps({'userId':'walter','sessionKey':'SESSION_KEY','ref':'e42','text':'YOUR TEXT'})
conn.request('POST', '/tabs/TAB_ID/type', body, {'Content-Type':'application/json'})
print(conn.getresponse().read().decode())
"

# Click element
docker exec webtop python3 -c "
import http.client, json
conn = http.client.HTTPConnection('localhost', 9378)
body = json.dumps({'userId':'walter','sessionKey':'SESSION_KEY','ref':'e42'})
conn.request('POST', '/tabs/TAB_ID/click', body, {'Content-Type':'application/json'})
print(conn.getresponse().read().decode())
"

# Send screenshot to Telegram
curl -s -X POST "https://api.telegram.org/bot$(vault get telegram/bot_token)/sendPhoto" \
  -F "chat_id=1146774717" -F "photo=@/tmp/svc-screenshot.png" -F "caption=Description"
```

## Camoufox Startup (if not running)

Camoufox can run in two modes:
1. **Webtop container** (default for cookie-injection workflows) — see below
2. **Local VPS** (Camoufox-max on port 9378) — used for services that don't need Mac cookies (e.g., Anthropic Console with email/password login). Process managed via Node.js directly.

```bash
# First time: patch viewport to 1920x1080
docker exec webtop bash -c "sed -i 's/viewport: { width: 1280, height: 720 }/viewport: { width: 1920, height: 1080 }/g' /tmp/camofox-browser/server.js"

# Start Camoufox in webtop
docker exec -d webtop bash -c 'cd /tmp/camofox-browser && DISPLAY=:1 NODE_ENV=development PORT=9378 node server.js > /tmp/camoufox.log 2>&1'

# Verify (after ~10s)
docker exec webtop bash -c 'tail -3 /tmp/camoufox.log'
# Should show: "camoufox launched" + "browser pre-warmed"

# Health check
docker exec webtop bash -c 'curl -s http://localhost:9378/health'
```

## User Intent Mapping (CRITICAL)

When the user says **"check mon twitter"**, **"mon compte X"**, **"ouvre Gemini"**, **"connecte-toi à Suno"**, etc., they mean:

1. **Extract cookies from Mac Brave** (fresh copy each time)
2. **Decrypt on host** using vault key
3. **Inject into Camoufox** webtop
4. **Navigate to the service** and browse the user's authenticated session

**This is NOT a search query.** "Mon twitter" = open x.com with his cookies and show what's on HIS feed/profile. Never confuse "check my account" with "search for X on the platform".

**"Mon twitter AI"** = check his X/Twitter feed focused on AI content, or navigate to his AI-curated list. NOT "search Twitter for AI".

Known accounts:
- **X/Twitter**: @earndeel (user_id: 1575827511124295). Premium+, certified. Custom lists: "Artificial Intelligence", "Gaming".
- **Suno**: Clerk auth via cookies
- **Grok**: x.com/grok, same X cookies

**Pitfall**: Do NOT ask the user for their handle or credentials you should already have. If the user says "mon twitter", you have the cookies — use them. Asking "quel est votre handle ?" when you could just connect is a failure mode that causes extreme frustration.

## Service Shortcuts

| Command | Service | URL | User's Account |
|---------|---------|-----|----------------|
| `aiprimetech` | AI Prime Tech | aiprimetech.io | earndeel@gmail.com (LocalStorage auth). **API key groups**: Claude Max, Image-2, Codex. See `references/aiprimetech-api.md` |
| `gemini` | Google Gemini | gemini.google.com/app | lucas.jouvencon@gmail.com |
| `suno` | Suno AI Music | suno.com | Clerk auth |
| `grok` | Grok (xAI) | grok.com | lucas.jouvencon@gmail.com |
| `chatgpt` | ChatGPT | chatgpt.com | — |
| `claude` | Claude | claude.ai | — |
| `youtube` | YouTube | youtube.com | — |
| `twitter` | X/Twitter | x.com | @earndeel |
| `facebook` | Facebook | facebook.com | — |
| `instagram` | Instagram | instagram.com | evolvedsprm |
| `bumble` | Bumble | bumble.com | — (cookies only, use Brave in Webtop) |
| `bumble` | Bumble | bumble.com/app | Lucas (via cookies) |
| `bumble` | Bumble | bumble.com/app | Lucas (use Brave in Webtop, NOT Camoufox — see references/bumble-webtop-notes.md) |
| `hailuo` | Hailuo AI | hailuoai.video | lucas.jouvencon@gmail.com (Stripe billing, NANONOBLE PTE. LTD.) |
| `anthropic` | Anthropic Console | console.anthropic.com | earndeel@gmail.com (Clerk OTP auth, billing/plan management) |

## Tab Lifecycle (RAM Management)

**Always close tabs after use.** Open tabs consume ~200MB each in Camoufox.

```python
# Close tab
h = http.client.HTTPConnection('localhost', 9378, timeout=5)
h.request('DELETE', '/tabs/TAB_ID?userId=walter')
```

Pattern: inject → navigate → interact → screenshot/extract → close. Never leave tabs open overnight.

## Performance Expectations
# Correct way to send formatted message
curl -X POST "https://api.telegram.org/bot{TOKEN}/sendMessage" \
  -F "chat_id={CHAT}" \
  -F "text={html_text}" \
  -F "parse_mode=HTML"
```

## User Intent Interpretation

**"Checker mon [service]"** = connect via cookies and check the USER'S OWN ACCOUNT (profile, stats, notifications, engagement), NOT browse the general feed.

For X/Twitter specifically:
- "Checker mon Twitter" → navigate to `https://x.com/{user_handle}` (profile page), NOT `https://x.com/home`
- Check: posts count, followers, following, notifications, engagement metrics
- Report as text summary first; screenshot only if explicitly requested
- User's X handle: `@earndeel` — save in memory, never ask again

**General rule:** When the user says "mon [service]" or "mon compte", they own it. Navigate to their profile/dashboard, not the service's home page.

## Performance Expectations

| Operation | Time | Notes |
|-----------|------|-------|
| Cookie extract (1 SSH call, all services) | ~5s | Mac must be awake |
| Decrypt + split on host | ~0.5s | Python with pycryptodome |
| Inject cookies (single batch) | ~0.5s | 100-150 cookies |
| Open 3 tabs in parallel | ~8s | ThreadPoolExecutor, 3 workers |
| Screenshot per tab | ~2s | 200-600KB PNG |
| Snapshot per tab | ~1-2s | 15-30K chars text |
| Close tab | ~0.5s | Always close after use |
| **Total: 3 services open** | **~15s** | vs ~3min sequential |

## Troubleshooting

**"Cette page n'existe pas" on X list**: Wrong list ID. Navigate to `https://x.com/{username}/lists` and click the list from there.

**Snapshot shows "Sign in" button**: Cookies expired or not injected. Re-extract from Mac Brave (fresh copy of Cookies DB).

**Cloudflare Turnstile on Grok**: Activate Tailscale exit node: `tailscale set --exit-node=100.127.150.1`. Container inherits host routing.

**Scroll timeout on X**: Increase timeout to 20s+. Snapshot still works even if some scrolls fail.

**Camoufox not responding**: Check health: `docker exec webtop bash -c 'curl -s http://localhost:9378/health'`. If dead, restart (see Camoufox Startup section).

## Further reading (moved out of this file on 2026-11-01, unchanged)

- `references/one-shot-script.md` — The full one-shot script for a single service.
- `references/spa-and-site-specific.md` — SPA fallbacks (Brave in Webtop, config extraction, execution failures, Ant Design invisible modals, scroll via JS), localStorage-auth services, Cloudflare Turnstile, site notes (Bumble, AIPrimeTech), static previews.
- `references/x-twitter-scraping.md` — X/Twitter cumulative and list scraping.
- `references/telegram-and-analysis.md` — Sending results and images to Telegram, image analysis, the dating-profile analysis workflow.
- `references/pitfalls.md` — All known pitfalls — read before debugging a failing service.

