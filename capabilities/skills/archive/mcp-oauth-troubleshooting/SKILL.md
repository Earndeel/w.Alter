---
name: mcp-oauth-troubleshooting
description: Troubleshoot OAuth-based remote MCP servers on headless or SSH Hermes hosts, including callback redirects, stale dynamic clients, and probe timeout workarounds.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [MCP, OAuth, troubleshooting, headless, SSH]
    related_skills: [native-mcp, mcporter, hermes-agent]
---

# MCP OAuth Troubleshooting

## When to use

Use this when connecting a remote HTTP MCP server that authenticates via browser OAuth, especially from a headless VPS, SSH session, TUI, or gateway host.

## Workflow

1. Configure the MCP server with HTTP transport and OAuth enabled.
2. Start the OAuth login in a real interactive terminal wrapper so the paste prompt can accept the callback URL:

```bash
script -q -c 'hermes mcp login <server>' /tmp/<server>-mcp-login.typescript
```

3. Open the printed authorization URL in a local browser.
4. After login, the browser usually lands on a localhost callback URL that cannot load locally because the listener is on the remote host. This is expected.
5. Copy the full final browser URL, or just the query part containing `code=` and `state=`, and submit it to the waiting login process.
6. Verify by testing the MCP connection and checking that tools are discovered before declaring success.

## Pitfalls

### Redirect URI mismatch after retries

If the provider says the `redirect_uri` does not match a pre-registered redirect URL, the local OAuth cache may contain a stale dynamic client registered for a previous callback port. Remove the cached OAuth files for that server, then start a fresh login.

Pattern:

```bash
rm -f <hermes-home>/mcp-tokens/<server>*.json <hermes-home>/mcp-tokens/<server>*.bak
```

Do not preserve a stale dynamic client when the callback port has changed.

### Login times out despite larger MCP config timeouts

Some Hermes CLI MCP login/probe paths can still use a shorter probe timeout than the server config. If `hermes mcp login <server>` dies around 40 seconds while the user is still completing browser auth, first check whether the login helper is passing `connect_timeout` through to `_probe_single_server`; patching that path is cleaner than asking the user to race OAuth.

Fallback explicit probe pattern:

```python
import yaml
from hermes_cli.mcp_config import _probe_single_server

with open('<hermes-home>/config.yaml') as f:
    cfg = yaml.safe_load(f)['mcp_servers']['<server>']

print(_probe_single_server('<server>', cfg, connect_timeout=600))
```

Wrap that script in `script -q -c ...` when the callback paste prompt must be interactive. If the runtime is non-interactive and no cached token exists, use `hermes mcp login <server>` from a PTY instead of the Python probe.

### Host-sensitive redirect URI providers

Some hosted OAuth MCP providers bind dynamic clients to the exact redirect host and may reject `http://127.0.0.1:<port>/callback` while accepting `http://localhost:<port>/callback`. If the provider's browser page returns `redirect_uri mismatch` even after purging stale token/client files, retry with an OAuth config option or code path that emits `localhost` in the authorization URL and dynamic client metadata.

Keep callback handling strict:
- Use only the latest authorization URL. Every retry rotates `state` and `code_challenge`; stale callbacks produce `State parameter mismatch`.
- Treat the user's message containing `http://localhost:<port>/callback?code=...&state=...` as the callback payload, even if background-process completion notices arrive nearby. Process notifications are logs; the user's callback URL is the action item. Do not dismiss it as stale unless its `state` differs from the currently printed authorization URL.
- **⚠️ WHEN THE USER SENDS A CALLBACK URL, TRY CURL FIRST — DO NOT RESTART THE FLOW.** If `hermes mcp login <server>` is running (background + PTY), its HTTP listener is alive on the printed port. Deliver the code with: `curl -sS 'http://localhost:<port>/callback?code=...&state=...'` from the Hermes host, then poll for completion. Only restart if curl returns a connection error (no listener on that port) or the token exchange fails. Restarting the flow invalidates the user's just-provided authorization code — they must re-authorize, which wastes a round-trip and causes frustration.
- If process stdin is unavailable AND no listener is reachable (custom script, non-`hermes mcp login` flow), use the FIFO fallback pattern — see `scripts/oauth-fifo-callback.py`.
- When testing code changes, run the repo venv's pytest (`venv/bin/python -m pytest ...`) rather than system Python if async pytest plugins are installed only in the venv.

See `references/higgsfield-oauth-headless.md` for the Higgsfield case pattern.

### Tailscale bypass — preferred when both hosts are on the same tailnet

When the Hermes host and your local machine share a Tailscale tailnet, skip the paste-and-pray flow entirely. Bind the callback server to `0.0.0.0`, register the OAuth client with the Tailscale IP as `redirect_uri`, and let the browser redirect hit the Hermes host directly via the tailnet. No copy-paste, no state mismatch, no PTY stdin races.

Requirements: both machines on the same Tailscale tailnet, callback port reachable on the tailnet interface.

Full technique and pitfalls: `references/tailscale-oauth-bypass.md`.
Reusable script: `scripts/oauth-tailscale-callback.py`.

### FIFO fallback — when neither submit nor curl works

When `process submit` is unavailable and no existing `hermes mcp login` listener is running (e.g., custom OAuth scripts), use a named pipe (FIFO) to deliver the callback code. The script opens a FIFO in non-blocking read mode, polls it alongside the HTTP server, and the agent writes the user's callback URL into the FIFO via `echo '<url>' > <fifo_path>`.

Reusable script: `scripts/oauth-fifo-callback.py`. Usage pattern in agent context:

```bash
# 1. Start the FIFO-based OAuth flow (background)
venv/bin/python scripts/oauth-fifo-callback.py \
  --server-url https://mcp.example.com/mcp \
  --token-dir ~/.hermes/mcp-tokens \
  --server-name myserver &
# Wait for AUTH_URL:... in output, give URL to user.

# 2. When user provides redirect URL, deliver via FIFO:
echo 'http://localhost:48461/callback?code=...&state=...' > /tmp/oauth_fifo_myserver

# 3. Script exchanges code, saves tokens, prints SUCCESS.
```

### Do not confuse auth success with config success

Adding the server to `mcp_servers` only makes Hermes know about it. OAuth is not complete until tokens are stored and the server lists tools successfully.

### Token filename: `<server>.json` NOT `<server>.tokens.json`

Hermes' `mcp_oauth.py` resolves the token path as `_get_token_dir() / f"{server_name}.json"` — the bare server name, no `.tokens` infix. Client metadata is `<server>.client.json`. If a manual OAuth script saves to `<server>.tokens.json`, `hermes mcp test` will report "no cached tokens found" even though the file exists. Fix: rename `<server>.tokens.json` → `<server>.json`, then retry `hermes mcp test`.

## Verification

- The login command exits successfully.
- The MCP test/list path discovers tools for the server.
- A new Hermes session is started after adding the server, because MCP tool discovery happens at startup.

### Direct curl verification (when `hermes mcp test` isn't available)

When tokens were saved manually (not via `hermes mcp login`), or when the session can't access `hermes mcp test`, verify the MCP connection directly against the endpoint:

```bash
ACCESS_TOKEN=$(python3 -c "import sys,json; print(json.load(open('/root/.hermes/mcp-tokens/<server>.json'))['access_token'])")

curl -sS -X POST <mcp-url> \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -3
```

If the SSE `data:` line contains `"result":{"tools":[...]}` — the MCP server is fully functional. The access token is valid and tools are callable. Hermes may not have registered them in the active session's tool registry (hot-reload limitation), but direct curl calls to `tools/call` work immediately.