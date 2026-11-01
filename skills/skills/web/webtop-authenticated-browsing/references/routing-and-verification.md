## Architecture

```
Mac Brave (CDP:9222) ──SSH──→ Cookies ──inject──→ Camoufox host (port 9377, headless Xvfb)
                                              └──→ Camoufox-in-Webtop (port 9378, Selkies-visible)
                                              └──→ Webtop Chromium (CDP:9223, fallback)
                                                        ↓
                                                  Screenshots + Click/Scroll/Type
```

## Decision Tree

```
Need authenticated browsing?
  ├─ Cloudflare-protected site?
  │    └─ Camoufox + auth-only cookies (NOT cf_clearance). Let Camoufox get its own cf_clearance.
  ├─ Anti-bot site (FB, DataDome)?
  │    ├─ User needs to SEE the browser? → Camoufox-in-Webtop (visible, Selkies)
  │    └─ Agent-only interaction? → Camoufox host (headless Xvfb, programmatic)
  ├─ Normal site, need auth?
  │    └─ Camoufox + auth cookies (fastest path)
  ├─ User says "ouvre le moi" / wants to SEE it?
  │    ├─ Open directly on Mac Brave: `ssh mac "open -a 'Brave Browser' '<url>'"`
  │    └─ If Mac not available → Camoufox-in-Webtop (visible on Selkies HTTPS:3001)
  ├─ Just need API token?
  │    └─ Extract token → vault → curl
  └─ Need real Mac browser fingerprint (DataDome strict)?
       └─ brave-walter CDP 9226 (real macOS fingerprint, SSH tunnel)
```

**Key rule**: When Monsieur says "ouvre le moi" — open it on his Mac Brave via SSH immediately. Don't suggest Webtop URLs or give instructions. Just do it.

**NEVER use Mac Brave CDP directly** — it opens visible tabs/pop-ups on Monsieur's screen.

**NEVER inject cf_clearance across browsers** — Cloudflare binds it to the fingerprint. Always inject auth-only cookies and let the target browser get its own cf_clearance.

## Parallelization Pattern

When the workflow requires both cookie extraction and browser setup, run them concurrently:

```python
# Background: cookie extraction from Mac
terminal("ssh mac 'cp ~/.../Cookies /tmp/cookies.db && sqlite3 /tmp/cookies.db ...' > /tmp/raw_cookies.txt && python3 decrypt.py", background=True, notify_on_complete=True)

# Background: Camoufox health check + cf_clearance
terminal("curl -s http://localhost:9377/health && curl -s -X POST http://localhost:9377/tabs -d '{\"url\":\"https://target.com\"}' && sleep 12 && curl -s http://localhost:9377/tabs/:id/snapshot", background=True, notify_on_complete=True)

# When both complete: inject auth cookies + navigate
```

This cuts total time by ~60% vs sequential execution (tested: 85s parallel vs 25min sequential with troubleshooting).

## Verification

- [ ] Camoufox health: `curl http://localhost:9377/health`
- [ ] Webtop CDP: `curl http://172.17.0.3:9223/json/version`
- [ ] Mac Brave CDP: `ssh lucasjouvencon@100.127.150.1 "curl -s http://localhost:9222/json/version"`
- [ ] Cookie injection: `POST /sessions/walter/cookies` → `{"ok": true}`
- [ ] Facebook auth: navigate to `/marketplace`, screenshot shows profile picture + logged-in UI
