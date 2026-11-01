# Higgsfield OAuth Renewal via SSH Tunnel

When MCP tokens expire and `hermes mcp reauth higgsfield` fails, use the `higgsfield` CLI
with an SSH tunnel for callback routing.

## Prerequisites
- `@higgsfield/cli` installed globally (`npm install -g @higgsfield/cli`)
- User has SSH access to VPS and a browser for Google OAuth

## Steps

1. **Start auth on VPS**: `cd /root && higgsfield auth login`
   → Prints Clerk OAuth URL + listens on `localhost:8766`

2. **User sets up tunnel** from local machine:
   `ssh -L 8766:localhost:8766 root@<vps-ip>`

3. **User opens URL** in browser → Google login → consent → redirects to
   `localhost:8766/callback?code=...` → tunnel routes to VPS

4. **Verify**: `higgsfield auth token` → returns `oat_...` bearer token

5. **Set workspace** (required for CLI generation):
   `higgsfield workspace list` then `higgsfield workspace set <id>`

6. **Use token for direct MCP**: `curl ... -H "Authorization: Bearer $(higgsfield auth token)" ...`

## Pitfalls
- CLI needs workspace set before `generate create`
- Trial accounts: `generate create` fails with `only_mcp_usage_on_trial_is_available` → use MCP directly
- `hermes mcp test higgsfield` times out even with valid tokens → use curl
