# OAuth Renewal — Working vs Dead-End Approaches

## ✅ Working: CLI + SSH Tunnel

```bash
# 1. VPS: start auth login (opens callback server on :8766)
higgsfield auth login
# → prints URL for user's browser

# 2. User's Mac (separate terminal):
ssh -L 8766:localhost:8766 root@<vps-ip>

# 3. User: open URL in Mac browser → login → redirected to localhost:8766/callback?code=XXX
# 4. User copy-pastes the full redirect URL to agent

# 5. VPS: curl the callback (tunnel routes to CLI's callback server)
curl "http://localhost:8766/callback?code=XXX&state=YYY"

# 6. VPS: get fresh token
higgsfield auth token
# → oat_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

## ❌ Dead Ends

### Camoufox headless browser
Does NOT work for Higgsfield OAuth. The Google login page triggers anti-bot detection even with Camoufox. The SSH tunnel approach is faster, simpler, and reliable.

### Direct OAuth PKCE via curl
The MCP server at `mcp.higgsfield.ai` doesn't expose standard OAuth endpoints (no `/oauth2/authorize`, no `.well-known/oauth-authorization-server` with usable metadata). The CLI handles the OAuth dance internally.

### Trying to register a custom client
`POST /oauth2/register` returns `404 Not Found`. Only the pre-registered client ID (`sRGCQJvvJkPrrtRj`) works, and it's bound to `localhost:8766/callback`.