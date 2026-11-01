---
name: webtop-authenticated-browsing
description: "Authenticated browsing via Camoufox or Webtop Chromium with Mac Brave cookies. Cookie extraction, injection, anti-detect navigation, screenshots, click/scroll/keyboard interaction. Also covers: webtop chromium cdp."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [browser, cdp, cookies, auth, camoufox, webtop, brave, mac, anti-detect]
    related_skills: [hermes-camoufox-setup, playwright-cdp-browser-control]
---

# Webtop Authenticated Browsing

> **State on 2026-11-01.** To act as Monsieur on a site, the normal path is `walter_browse` (Hermes) or `browser_session` + `walter-browser` (Claude Code, Codex, DSH): his cookies are injected server-side and the agent only gets metadata. Never extract Brave cookies, keychain keys or LevelDB yourself; the extraction steps below are history and debugging material. Entry: `walter-browse-orchestrator`.

Browse sites where Lucas is logged in on Mac Brave, using anti-detect Camoufox or Webtop Chromium with injected cookies. Covers the full pipeline: extract → inject → navigate → interact → screenshot.

## Always-on rules

- When Monsieur says "ouvre le moi" — open it on his Mac Brave via SSH immediately. Don't suggest Webtop URLs or give instructions. Just do it.
- NEVER connect Scrapling/Playwright to main Mac Brave CDP (port 9226).
- Use Camoufox (localhost:9377) or Webtop Chromium (localhost:9223) for all browsing.
- The Mac Brave CDP is ONLY for cookie extraction (Step 1) via raw `websockets` + `Storage.getCookies`, never for navigation.
- NEVER inject `cf_clearance` from one browser into another.
- Inject ONLY auth cookies (session tokens, Keycloak, PHPSESSID), then let the target browser navigate to the site and obtain its OWN `cf_clearance` automatically.
- Preferred: Keychain decryption (works when main Brave has no CDP — which is the normal case).
- Refs reset after navigation: Must re-snapshot before clicking in Camoufox.
- Always `SIGTERM` first, wait 30s, then `SIGKILL` as fallback.
- Selkies requires HTTPS: Use `https://<host>:3001` instead.

## When to Use

- Need to browse a site where Lucas has an active session on Mac Brave
- Scrapling/headless tools get blocked by anti-bot (Facebook, Cloudflare, etc.)
- Need screenshots + click/scroll/keyboard interaction on authenticated pages
- Need human-like browsing behavior (not API calls)

## Step 3: Screenshot + Analysis Pattern

```python
# At each interaction step, screenshot + vision_analyze
page.screenshot(path="/tmp/step-N.png")
# Use vision_analyze tool on /tmp/step-N.png to understand what's visible
# Use snapshot (accessibility tree) to find clickable refs
```

## Account-Risk Policy

- Prefer **Camoufox/browser navigation** over internal API calls
- Do NOT create cron polling jobs against unofficial APIs
- Do NOT send messages through internal APIs unless Monsieur accepts risk
- Read-only, one-shot checks only, on user request
- Tinder: `localStorage.getItem('TinderWeb/APIToken')`, API `api.gotinder.com`, no mass scraping

## References (read with skill_read(name, file_path=...))

- `references/camoufox-host.md` — Read when starting or controlling host Camoufox, importing cookies through its API, or using behavioral simulation and CAPTCHA modules.
- `references/cookie-extraction.md` — Read before extracting or injecting Mac Brave cookies, converting expiry timestamps, or handling SQLite and Keychain fallbacks.
- `references/macos-cookie-decryption.md` — Read for detailed macOS cookie decryption analysis, encryption scheme details, and Keychain access methods.
- `references/northwest-registered-agent.md` — Read when browsing Northwest Registered Agent for its Keycloak authentication flow, SPA behavior, and document download patterns.
- `references/routing-and-verification.md` — Read when choosing the browser and visibility path, coordinating cookie extraction with browser setup, or verifying the session.
- `references/site-workflows-and-downloads.md` — Read for Google Flow, Facebook, Instagram, or LinkedIn workflows, or when capturing S3/CDN download URLs.
- `references/troubleshooting.md` — Read when diagnosing browser, cookie, CDP, Cloudflare, container, display, or Keychain failures.
- `references/webtop-browsers.md` — Read when launching visible browsers in Webtop, choosing noVNC or Selkies setup, using Chromium CDP, or managing browser persistence.

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **webtop-chromium-cdp** — Webtop container administration: Chromium + CDP startup script, stale Singleton locks, s6-overlay boot service, cron persistence, verifying browser access.
  Read `references/merged-webtop-chromium-cdp/webtop-chromium-cdp.md`.
