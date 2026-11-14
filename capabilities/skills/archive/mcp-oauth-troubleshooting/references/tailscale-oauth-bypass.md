# Tailscale OAuth Callback Bypass

## When to use

When the Hermes host and your local machine are on the same Tailscale tailnet, you can avoid the paste-based callback fallback entirely. Instead of fighting with `process.submit`, PTY stdin races, and state mismatch retries, let the OAuth redirect hit the Hermes host directly via the Tailscale IP.

## Why the paste flow fails

`hermes mcp login <server>` in `pty=true` mode has subtle stdin handling issues when driven via `process(action='submit')`. The paste thread and the HTTP callback listener race — and often neither wins cleanly. The flow restarts with a new `state`/`code_challenge`, invalidating any callback URL the user copied.

## Tailscale bypass pattern

1. Find the Hermes host's Tailscale IP:

```bash
tailscale status --json | python3 -c "
import json,sys
d=json.load(sys.stdin); s=d['Self']
print(f\"IP: {s['TailscaleIPs'][0]}\")"
```

2. Build a direct OAuth flow that:
   - Binds the callback HTTP server to `0.0.0.0` (all interfaces, including Tailscale)
   - Registers the OAuth client with `redirect_uri` pointing to the Tailscale IP + port
   - Generates PKCE, shows the authorization URL, waits for the callback
   - Exchanges the authorization code for tokens
   - Saves tokens to `~/.hermes/mcp-tokens/<server>.*.json`

3. The user opens the authorization URL in their browser. After authorizing, Higgsfield (or any OAuth provider) redirects to `http://<tailscale-ip>:<port>/callback`. Since both machines are on the same tailnet, the redirect reaches the Hermes host directly.

4. No copy-paste, no state mismatch, no timeout race.

## Working script

See `scripts/oauth-tailscale-callback.py` for a reusable implementation.

## Provider config

The script places `client.json` and `tokens.json` in the standard MCP token directory. After the script exits successfully, the MCP server can authenticate using these cached tokens. No config changes needed — Hermes picks them up on next MCP connection.

## Pitfalls

- **Tailscale IP changes**: If the Hermes host gets a new Tailscale IP, you must re-run the flow.
- **Firewall**: Ensure the callback port is reachable on the Tailscale interface (it should be by default on most tailnets).
- **Port conflicts**: Pick a fixed port or let the OS assign one. If fixed, ensure nothing else is on it.
- **Stale tokens**: Purge `~/.hermes/mcp-tokens/<server>.*.json` before starting a fresh flow, or the old client registration may interfere.
- **CRITICAL — Provider HTTP redirect restriction**: Some OAuth providers reject non-localhost HTTP redirect URIs. Higgsfield, for example, returns: `error=invalid_request&error_description=Redirect+URL+is+using+an+insecure+protocol%2C+http+is+only+allowed+for+hosts+with+suffix+%27localhost%27`. For these providers the Tailscale bypass cannot work — the provider refuses to redirect to `http://<tailscale-ip>:<port>/callback`. Fall back to the standard paste-based flow with `redirect_host: localhost` and a PTY-wrapped `hermes mcp login <server>`.
