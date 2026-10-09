# Webtop Non-Headless Camoufox

Google CAPTCHA is triggered by headless browser fingerprint (TLS, JS properties), NOT by IP type. Even residential IPs (Mac Tailscale exit node) don't help for **Lens** — but regular Google Images search works fine from non-headless Camoufox.

**Tailscale exit node context**: The VPS (Oracle, IP 129.150.52.60) uses the Mac as Tailscale exit node. All VPS traffic exits via the Mac's residential Thai IP (124.120.206.170). This is confirmed working — `curl` from VPS returns the Mac's IP. Google CAPTCHA comes from browser fingerprint, not IP type.

## What works and what doesn't

| Feature | Headless (port 9377) | Non-headless Webtop (port 9378) |
|---------|---------------------|--------------------------------|
| Google homepage | CAPTCHA | ✅ Works |
| Google text search | CAPTCHA | ✅ Works (until rate limit) |
| Google Images search (`udm=2`) | CAPTCHA | ✅ Works (until rate limit) |
| Google Lens (camera upload / `/uploadbyurl`) | CAPTCHA/403 | ❌ 403 Forbidden |
| Bing (all features) | ✅ Works | ✅ Works |
| Yandex (all features) | ✅ Works | ✅ Works |

## Setup

Camoufox is pre-installed in the Webtop container. Server runs on port 9378 inside the container.

```bash
# Check if Camoufox server is running in Webtop
docker exec webtop curl -s http://localhost:9378/health

# Port 9378 is NOT mapped to host. Access via docker exec:
docker exec webtop curl -s -X POST http://localhost:9378/tabs \
  -H "Content-Type: application/json" \
  -d '{"userId":"walter","sessionKey":"ggl","url":"https://www.google.com/"}'

# Navigate, snapshot, screenshot all via docker exec
docker exec webtop curl -s -X POST "http://localhost:9378/tabs/{TAB_ID}/navigate" \
  -H "Content-Type: application/json" \
  -d '{"userId":"walter","sessionKey":"ggl","url":"https://www.bing.com/images/search?q=..."}'

# Copy screenshots to host
docker exec webtop curl -s "http://localhost:9378/tabs/{TAB_ID}/screenshot?userId=walter&sessionKey=ggl" -o /tmp/screenshot.png
docker cp webtop:/tmp/screenshot.png /tmp/screenshot.png
```

## Pitfalls

- **Google rate limits aggressively**: After 5-8 searches, even non-headless gets CAPTCHA. Wait 5-10 minutes or switch to Bing. The rate limit resets per-IP; it's tied to request volume, not session count.
- **Scrapling bypass when Camoufox is CAPTCHA'd**: Use `mcp_scrapling_stealthy_fetch(solve_cloudflare=True)` or `mcp_scrapling_open_session(session_type="stealthy", solve_cloudflare=True)` + `mcp_scrapling_screenshot()`. Scrapling has a different browser fingerprint and bypasses Google's rate limit. Returns text content with image source labels, or screenshots for visual analysis. This worked when both headless and non-headless Camoufox were blocked.
- **Google Images vs Google Lens**: Google Images (regular image search with `udm=2`) works fine from non-headless Camoufox. Only Google Lens (the camera-icon upload feature or `/uploadbyurl` endpoint) returns 403 Forbidden. If you need reverse image search, use Yandex instead.
- **JSON parse errors**: Webtop snapshot output may contain control characters. Always use `json.loads(raw, strict=False)` or save to file first. The `execute_code` helper `json_parse()` handles this automatically.
- **docker exec overhead**: Each `docker exec curl` adds ~1-2s latency. Batch operations in a single `execute_code` script with embedded docker exec calls.
- **Tab IDs are persistent**: Reuse tabs rather than creating new ones to avoid accumulating browser state.
- **Selkies (port 3001)**: For interactive debugging, open `https://100.91.35.121:3001` to see the actual browser via the shared desktop. This is NOT noVNC.
