# Tested Services — Auth Details & Anti-Bot Matrix

## Service Status (tested 2026-05-31)

| Service | Auth Method | Key Cookies | Anti-Bot | IP Requirement | Status |
|---------|-------------|-------------|----------|----------------|--------|
| **Gemini** | Google cookies | SID, HSID, SSID, APISID, SAPISID, __Secure-*PSID | None | VPS OK | ✅ |
| **Suno** | Clerk auth | __client, __client_uat, __session, sessionid (studio-api) | None | VPS OK | ✅ |
| **Grok** | X cookies + Clerk | __client, __client_uat + X auth cookies | Cloudflare Turnstile | **Residential IP required** | ✅ (with exit node) |
| **X/Twitter** | X auth cookies | auth_token, ct0, twid | DataDome (soft) | Residential preferred | ✅ |
| **ChatGPT** | OpenAI cookies | __Secure-next-auth.session-token, cf_clearance | Cloudflare | Residential preferred | ⚠️ Untested |
| **Claude** | Anthropic cookies | sessionKey, __cf_bm | Cloudflare | Residential preferred | ⚠️ Untested |

## Per-Service Notes

### Gemini (gemini.google.com)
- Auth via Google account cookies (shared with YouTube, Google Drive, etc.)
- No anti-bot on regular pages. Google Lens has separate 403 blocking.
- Shows "Sign in" button when not authenticated, user avatar when authenticated.
- French locale: "C'est à vous, Lucas !" greeting, "Demander à Gemini" input.

### Suno (suno.com)
- Auth via Clerk (`__client` + `__client_uat` JWT cookies).
- `sessionid` cookie from `studio-api.prod.suno.com` is also needed.
- No anti-bot. Landing page shows "Sign in with Google" modal when not auth'd.
- User: earndeel, shows credit count in sidebar.

### Grok (grok.com)
- Uses Clerk auth (same pattern as Suno).
- **Cloudflare Turnstile** blocks datacenter IPs even with valid cookies.
- **Fix**: `tailscale set --exit-node=100.127.150.1` to route through Mac's residential IP.
- Container inherits host routing — no per-container config needed.
- Deactivate exit node after use if latency is an issue.

### X/Twitter (x.com)
- Auth via `auth_token`, `ct0` cookies.
- DataDome anti-bot is soft — cookies + Camoufox pass without challenge.
- Residential IP recommended but VPS works for basic feed access.
- Feed snapshot: each tweet = `article "DisplayName @handle ... metrics"`.
- Lists: navigate to `https://x.com/i/lists` → find list → click → feed.
- Scroll timeout: use 20s+ timeout (default 10s may fail).
- ~7 tweets per snapshot without scrolling, ~12 with 10 scrolls.
- **Cumulative scraping**: 25 scrolls ≈ 44 posts in ~90s (~1.7 new/scroll).
- **Anti-detection**: Camoufox `humanize=True` + residential IP = 0 blocks in testing (25 scrolls).
- **Script**: `scripts/x-cumulative-scraper.py` for ready-to-run cumulative scraping.

## Cloudflare Turnstile — Root Cause

Cloudflare checks:
1. **IP reputation** — datacenter IPs flagged, residential IPs pass
2. **TLS/JS fingerprint** — Camoufox's modified Firefox fingerprint triggers detection
3. **Behavioral signals** — mouse movements, timing patterns

**Solution**: Residential IP via Tailscale exit node. Cookies alone are NOT enough for datacenter IPs.

## Cookie Domains Reference

| Service | Domains to query in SQLite |
|---------|---------------------------|
| Gemini | `google`, `gemini` |
| Suno | `suno` |
| Grok | `grok`, `x.ai` |
| X/Twitter | `x.com`, `twitter` |
| ChatGPT | `openai`, `chatgpt` |
| Claude | `claude`, `anthropic` |
| YouTube | `google`, `youtube` |
| Facebook | `facebook` |
| Instagram | `instagram` |
