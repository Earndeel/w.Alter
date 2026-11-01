# xAI Authentication for Hermes Agent

## Two Access Paths

### 1. SuperGrok OAuth (recommended for Premium+ subscribers)
- **Command**: `hermes auth add xai-oauth` (opens browser) or `hermes auth add xai-oauth --no-browser` (prints URL)
- **Requires**: Browser interaction — must run on a machine with a browser, or use `--no-browser` and visit URL manually
- **What it gives**: Access to Grok models + x_search via subscription (no per-token cost)
- **Premium+ (38€/mois)** includes SuperGrok → OAuth works
- **Cost**: $0 with subscription
- **Pitfall**: `hermes auth add xai-oauth` without `--no-browser` tries to open a browser. On a headless VPS, it hangs. Use `--no-browser` or run on Mac.
- **Pitfall**: The OAuth flow requires TTY. In background mode, it fails with "open terminal failed: not a terminal". Use `pty=true` in terminal tool.

### 2. xAI API Key (for API credits)
- **Command**: `hermes auth add xai --type api-key --api-key "xai-..."` 
- **Console**: https://console.x.ai/team/{team_id}/api-keys
- **What it gives**: Direct API access to Grok models at per-token pricing
- **Pricing**: grok-4.3 = $1.25/M input, $2.50/M output
- **Pitfall**: API credits are SEPARATE from Premium+ subscription. Premium+ gives SuperGrok (web/app), not API credits. The console shows "You have no paid credits" even with Premium+.
- **Pitfall**: "RW cookie required but is missing" error when creating API keys → session issue. Re-login to console.x.ai, or clear cookies and re-authenticate with X.

## x_search Configuration

```yaml
x_search:
  model: grok-4.20-reasoning
  timeout_seconds: 180
  retries: 2
```

Enable: `hermes tools` → enable "X (Twitter) Search"

**Prerequisites**: Either SuperGrok OAuth OR XAI_API_KEY. OAuth takes priority when both configured.

## xAI Console Notes
- Team ID visible in URL: `https://console.x.ai/team/{uuid}/...`
- Existing API keys cannot be revealed (only name + partial ID visible)
- Creating new keys requires: login + paid credits OR working session cookie
- "Grok Business" section in sidebar = enterprise features

## Browser-Based Auth (fallback)
If CLI auth fails, use Brave CDP to:
1. Navigate to `https://console.x.ai`
2. Login with X account (OAuth flow)
3. Create API key manually
4. Extract key value from the confirmation dialog
5. Configure in Hermes: `hermes auth add xai --type api-key --api-key "xai-..."`

**Pitfall**: Don't use `context.clear_cookies()` to fix xAI console issues — it wipes ALL browser sessions. Use targeted cookie clearing instead.
