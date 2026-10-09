# OAuth Headless Renewal (via CLI + SSH tunnel)

When the Higgsfield MCP token expires and the standard OAuth flow is blocked (redirect_uri mismatch on a remote server), use the CLI to generate a new token.

## Flow

1. **Install CLI:** `npm install -g @higgsfield/cli`
2. **Start auth:** `higgsfield auth login` — prints a Clerk OAuth URL with PKCE challenge
3. **Create SSH tunnel from local machine:** `ssh -L 8766:localhost:8766 root@<vps>`
4. **Open the URL** on the local browser → Google login → authorize
5. **Redirect hits** `http://localhost:8766/callback?code=...&state=...` — forwarded through SSH tunnel to the VPS where `higgsfield auth login` is listening
6. **Confirm token:** `higgsfield auth token` — returns the new OAuth token

## Important

- The CLI runs a local HTTP server on port 8766 during auth
- The state parameter MUST match — don't craft your own URL, use the one printed by `higgsfield auth login`
- After auth: `higgsfield workspace set <id>` then `higgsfield workspace list --json` to verify
- Example: token = `oat_O5K3HXRR7JF52WHJEFWH96ME0FC0106J`

## Trial account restrictions (updated 2026-07-05)

| Model | Status |
|---|---|
| `cinematic_studio_3_0` | ✅ Works on trial (~80 credits/8s) |
| `kling3_0_turbo` | ❌ `only_mcp_usage_on_trial_is_available` |
| `kling-v1-6` | ❌ `only_mcp_usage_on_trial_is_available` |
| `veo3_1` | ❌ `only_mcp_usage_on_trial_is_available` |
| `wan2_2-t2v_turbo` | ❌ `only_mcp_usage_on_trial_is_available` |
| `gemini_omni` | ❌ Backend error (not trial-restricted, just broken) |
| `cinematic_studio_3_5` | ❌ Model unknown on this MCP instance |
| `gemini_flash` | ❌ Model unknown on this MCP instance |

Upgrading from trial to plus unlocks all blocked models. Plan is managed via `higgsfield workspace`.
