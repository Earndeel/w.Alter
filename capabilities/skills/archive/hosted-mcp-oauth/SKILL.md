---
name: hosted-mcp-oauth
description: Connect hosted HTTP MCP servers that require OAuth on headless or SSH Hermes hosts, including redirect paste-back workflows and verification.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [MCP, OAuth, headless, SSH, integrations]
    related_skills: [native-mcp, mcporter, hermes-agent]
---

# Hosted MCP OAuth

Use this skill when adding, authenticating, or troubleshooting hosted HTTP MCP servers that use OAuth instead of static API keys, especially from a headless VPS or SSH/TUI Hermes session.

## Trigger conditions

- User asks to connect a remote MCP endpoint with browser login/OAuth.
- `hermes mcp add ... --auth oauth` reports no cached tokens or cannot open a browser.
- The provider redirects to `127.0.0.1:<port>/callback` but the browser is on another machine.
- Ad-hoc MCP discovery works poorly because the client requests incompatible OAuth scopes.

## Workflow

1. Discover the official endpoint from the provider docs/site, then add it with native Hermes OAuth:
   ```bash
   hermes mcp add <name> --url <https://provider.example/mcp> --auth oauth
   ```

2. If discovery cannot complete because auth requires a browser, save the config only when the endpoint and auth method are clearly correct. The canonical shape is a YAML mapping:
   ```yaml
   mcp_servers:
     provider_name:
       url: https://provider.example/mcp
       auth: oauth
       enabled: true
       timeout: 180
       connect_timeout: 60
   ```

3. Check existing `mcp_servers` entries before listing/testing. If a server entry is accidentally stored as a JSON string instead of a YAML mapping, `hermes mcp list` can crash with `TypeError: string indices must be integers`. Normalize string-valued entries into maps before continuing.

4. Start OAuth login from a real TTY. In Hermes tool-driven terminal sessions, `pty=true` may still leave Python seeing `sys.stdin.isatty() == False`; wrap the command with `script`:
   ```bash
   script -q -c 'hermes mcp login <name>' /tmp/<name>-mcp-login.typescript
   ```
   For an interactive agent session, run this as a tracked background process so you can submit the pasted redirect later.

5. Give the user the printed authorization URL verbatim. On SSH/headless hosts, explain the redirect problem plainly: the provider will redirect to `http://127.0.0.1:<port>/callback` on the user's browser machine, while Hermes is listening on the remote host.

6. Ask the user to paste either:
   - the full final redirect URL, or
   - just the query portion: `?code=...&state=...`

7. Submit the pasted redirect into the waiting login process stdin, then verify:
   ```bash
   hermes mcp test <name>
   ```

8. Start a new Hermes session or run `/reload-mcp` so discovered tools enter the active tool registry.

## Higgsfield-specific notes

- Official endpoint observed: `https://mcp.higgsfield.ai/mcp`.
- Native OAuth config shape:
  ```yaml
  mcp_servers:
    higgsfield:
      url: https://mcp.higgsfield.ai/mcp
      auth: oauth
      enabled: true
      timeout: 180
      connect_timeout: 600
      oauth:
        timeout: 600
        redirect_host: localhost
  ```
- If Higgsfield returns `redirect_uri does not match any of the OAuth 2.0 Client's pre-registered redirect urls`, check whether Hermes generated `127.0.0.1` in the authorization URL. Higgsfield may require `localhost`; set `oauth.redirect_host: localhost`, delete stale Higgsfield MCP OAuth client/token cache files, and retry.
- If `npx mcporter list --http-url https://mcp.higgsfield.ai/mcp --name higgsfield` fails with `Invalid scope requested`, do not conclude the MCP is unusable. Use Hermes native OAuth; the working authorization URL can request scopes such as `openid email offline_access`.
- See `scripts/higgsfield_fifo_auth.py` for a standalone FIFO-based OAuth script that handles the full PKCE flow without relying on `hermes mcp login`. Use when tokens expired mid-session and re-auth is needed immediately without restarting Hermes. Run it as a background process, paste the user's callback URL into `/tmp/higgsfield_code` FIFO.
- See `references/higgsfield-mcp-oauth.md` for a compact incident recipe.
- See `references/higgsfield-model-catalog.md` for verified model IDs and the direct-curl MCP query pattern.
- **Tailscale bypass does not work for Higgsfield**: Higgsfield rejects non-localhost HTTP redirect URIs (`error=invalid_request ... http is only allowed for hosts with suffix 'localhost'`). Even with both machines on the same Tailscale tailnet, the provider won't redirect to `http://<tailscale-ip>:<port>/callback`. Use only the paste-based flow with `redirect_host: localhost`.

## Pitfalls

- Do not encode provider-specific failures as permanent negative facts. OAuth clients and scopes change; verify live.
- Do not paste tokens into `config.yaml`. OAuth tokens belong in Hermes' MCP token storage managed by `hermes mcp login`.
- Do not leave the task at “config added” if the user's goal was “connect”; complete OAuth and run `hermes mcp test` when the user can provide the redirect code.
- Do not use markdown link syntax for URLs when reporting to Monsieur; provide raw URLs or backticked URLs.

### Tokens on disk, but new session re-triggers OAuth

After a successful OAuth flow, tokens live under `~/.hermes/mcp-tokens/<server>.json` — **NOT** `<server>.tokens.json`. Hermes' `mcp_oauth.py` resolves the path as `_get_token_dir() / f"{server_name}.json"` (bare name, no `.tokens` infix). Client metadata is `<server>.client.json`. When the user does `/new`, Hermes restarts and may **re-trigger the OAuth login** — printing a fresh `localhost` authorization URL — even though valid token files exist. This is not a bug: it's the current hot-reload limitation.

**Before re-authenticating**, verify the token is still valid:

```bash
ACCESS_TOKEN=$(python3 -c "import json; print(json.load(open('/root/.hermes/mcp-tokens/<server>.json'))['access_token'])")
curl -sS -X POST <mcp-url> \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | head -3
```

If the token is valid, the MCP is accessible; Hermes just can't register it mid-session. Either re-authenticate (fast), or use direct curl calls for the current session (viable, slower). If the token is expired, use the refresh token or re-authenticate.

## Verification checklist

- `hermes mcp list` shows the server and does not crash.
- `hermes mcp test <name>` connects and lists tools.
- The next Hermes session exposes tools named with the `mcp_<server>_...` prefix.
- If this required editing Hermes code, run syntax checks and targeted MCP OAuth tests from the repo virtualenv (`venv/bin/python ...`), not system Python; system Python may lack pytest async plugins and make unrelated async tests fail.
- If full test collection fails on unrelated optional dependencies, report that blocker and still run the narrow MCP OAuth test files relevant to the patch.
