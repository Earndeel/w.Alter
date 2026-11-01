---
name: higgsfield-video-generation
description: Generate images and videos via Higgsfield's MCP server. Covers model catalog, video generation, pitfalls (OAuth headless, params wrapper, model IDs), and direct JSON-RPC fallback when transport is down.
---

# Higgsfield Video Generation

Generate images and videos via the Higgsfield AI platform through its MCP server (`mcp-higgsfield`).

## Quick Start

```json
// tools/call via MCP
{"name":"generate_video","arguments":{"params":{"model":"kling3_0","prompt":"Your prompt","aspect_ratio":"16:9","duration":8}}}
```

**CRITICAL**: The `params` key is REQUIRED inside `arguments`. The tool schema declares `params` as the only required top-level field. Sending `{"model":"...","prompt":"..."}` directly inside `arguments` will fail with "Invalid input: expected object, received undefined".

## Model IDs

Use `models_explore` with `action:"list"` or `action:"recommend"` to discover models. Correct IDs:

| Model ID | Provider | Notes |
|----------|----------|-------|
| `kling-v1-6` | Kling 1.6 | |
| `kling3_0_turbo` | Kling 3.0 Turbo | **NOT** `kling3_0` — that ID errors with "Something went wrong." Duration must be a number (8), not a string ("8s"). |
| `gemini_omni` | Gemini Omni Flash | Google's video model. Discover with `action:"search","query":"gemini"`. |
| `veo3_1` | Google Veo 3.1 | Ultra-realistic cinematic. |

| ID | Name | Provider | Type |
|---|---|---|---|
| `kling3_0` | Kling v3.0 | Kling | Video (multi-shot, audio sync) |
| `seedance_2_0` | Seedance 2.0 | Bytedance | Video (reference-driven) |
| `veo3_1` | Google Veo 3.1 | Google | Video (cinematic, ultra-realistic) |
| `cinematic_studio_video` | Cinema Studio Video | Higgsfield | Video (cinematic) |
| `cinematic_studio_2_5` | Cinema Studio Image 2.5 | Higgsfield | Image (up to 4K) |
| `nano_banana_2` | Nano Banana 2 | Google | Image |

**Gotcha**: `kling-v1-6` and `kling3_0` are both valid model IDs. Prefer `kling3_0_turbo` for fastest generation. Model IDs are discoverable via `models_explore` — don't guess.

## Trial Account Model Lockout

Most video models return `only_mcp_usage_on_trial_is_available` on trial/plus accounts, even with credits. Per testing on 2026-07-05:

- ✅ `cinematic_studio_3_0` — works
- ❌ `gemini_omni`, `kling3_0_turbo`, `kling-v1-6`, `veo3_1`, `wan2_2-t2v_turbo` — blocked
- ❌ `cinematic_studio_3_5` — does not exist (3.0 is latest)

Always run `models_explore(action:'list')` first to confirm what's reachable on your account.

**Trial account restrictions**: On trial workspaces, most video models are blocked with `{"error_type":"only_mcp_usage_on_trial_is_available"}`. Only `cinematic_studio_3_0` is confirmed to work. All others — `kling3_0_turbo`, `kling-v1-6`, `veo3_1`, `wan2_2-t2v_turbo`, `gemini_omni`, `gemini_flash` — are paywalled. Even when `plan_type` says `"plus"`, the backend may still enforce trial restrictions; the `error_type` in the response is authoritative.

**Checking credits**: `higgsfield workspace list --json` shows `credits`. After each generation, re-check — `cinematic_studio_3_0` costs ~80 credits per 8s video.

## OAuth Renewal via CLI (most reliable)

When the MCP transport is down or tokens are expired, the **CLI-based OAuth flow with SSH tunnel** is the most reliable method:

1. Start `higgsfield auth login` on the VPS — it prints an OAuth URL and listens on `localhost:8766`
2. Have the user SSH-tunnel from their local machine: `ssh -L 8766:localhost:8766 root@<vps-ip>`
3. User opens the printed URL in browser → Google OAuth → redirects to `localhost:8766/callback` → SSH tunnel routes it to VPS
4. After success, `higgsfield auth token` returns the bearer token usable for direct MCP calls

**Token reuse**: After auth, use the CLI token (`higgsfield auth token`) in MCP `Authorization: Bearer` headers — no need to sync with `mcp-tokens/`.

## Transport & OAuth Pitfalls

The MCP SSE transport can go down silently — the agent gets empty tool results or hangs.
When the MCP transport dies, `tool_call` returns `"MCP server 'higgsfield' transport is down; reconnect requested"`. Revive it:

```
hermes mcp test higgsfield
```

This reconnects the transport. The first call after revival usually succeeds.
### OAuth tokens expire in headless

Higgsfield uses OAuth 2.1 PKCE. Tokens stored at `~/.hermes/mcp-tokens/higgsfield.tokens.json` (opaque `oat_` prefix, not JWT).

In headless environments:
- `hermes mcp login higgsfield` requires an interactive terminal and will fail.
- `hermes mcp reauth higgsfield` fails with "no cached tokens found" even if the file exists — the transport layer loses track but the token itself may still work via curl.
- **Transport discrepancy**: when `hermes mcp test` says no tokens, try `curl` first — the token file may still be valid.
For full PKCE headless renewal flow (generate auth URL → user opens in browser → exchange code for tokens), see `references/oauth-headless-renewal.md`.

**SSH tunnel trick** (when OAuth redirect must land on the VPS): see `references/ssh-tunnel-oauth.md`. The `higgsfield auth login` CLI starts a server on port 8766; use `ssh -L 8766:localhost:8766` from the user's Mac to forward the callback.

**Model catalog**: see `references/model-catalog.md` for discovered model IDs.

- `hermes mcp test` will fail with "no cached tokens found" when tokens expire
- The refresh token endpoint (`/oauth2/token`) may return 404
- **Token expiry is asymmetric**: a token that successfully calls `tools/list` and `models_explore` may return `"Invalid or expired token"` for `generate_video`. Write operations enforce stricter validation. When you see this, re-authenticate — do not debug the request format.

**Workaround**: Run `hermes mcp login higgsfield` from an interactive terminal (Mac local) to complete the browser-based OAuth flow.

### Token cache
Tokens are stored at `~/.hermes/mcp-tokens/higgsfield.tokens.json`. They include `access_token` (opaque, `oat_...`), `refresh_token`, `id_token`, and `expires_in`.

## Support Files

- `references/oauth-renewal-patterns.md` — SSH-tunnel OAuth (✅) vs Camoufox/headless dead ends (❌)
- `references/trial-model-check.md` — Trial model availability matrix + credit tracking

## Direct JSON-RPC Fallback

When the MCP transport is down but tokens are still valid, call the API directly via curl:

```bash
# Initialize session
curl -sS 'https://mcp.higgsfield.ai/mcp' \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"hermes","version":"1.0.0"}},"id":1}'

# List models
curl -sS 'https://mcp.higgsfield.ai/mcp' \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"models_explore","arguments":{"action":"list"}},"id":1}'

# Generate video (NOTE: params wrapper required!)
curl -sS 'https://mcp.higgsfield.ai/mcp' \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"models_explore","arguments":{"action":"search"}},"id":2}'

# Generate a video
printf '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"generate_video","arguments":{"params":{"model":"MODEL_ID","prompt":"PROMPT","duration":8}}},"id":3}' > /tmp/hf.json
curl -sS --no-buffer 'https://mcp.higgsfield.ai/mcp' \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d @/tmp/hf.json
```

### Using the Higgsfield CLI

```bash
npm install -g @higgsfield/cli
higgsfield auth login       # needs SSH tunnel on VPS (see references/ssh-tunnel-oauth.md)
higgsfield auth token       # show current token
```

### Dynamic client registration

```bash
curl -sS 'https://mcp.higgsfield.ai/oauth2/register' \
  -H "Content-Type: application/json" \
  -d '{"redirect_uris":["http://127.0.0.1:19999/callback"]}'
```

## Trial Account Model Lockout

Most video models return `only_mcp_usage_on_trial_is_available` on trial/plus accounts, even with credits. Per testing on 2026-07-05:

- ✅ `cinematic_studio_3_0` — works
- ❌ `gemini_omni`, `kling3_0_turbo`, `kling-v1-6`, `veo3_1`, `wan2_2-t2v_turbo` — blocked
- ❌ `cinematic_studio_3_5` — does not exist (3.0 is latest)

Always run `models_explore(action:'list')` first to confirm what's reachable on your account.

**Trial account restrictions**: On trial workspaces, most video models are blocked with `{"error_type":"only_mcp_usage_on_trial_is_available"}`. Only `cinematic_studio_3_0` is confirmed to work. All others — `kling3_0_turbo`, `kling-v1-6`, `veo3_1`, `wan2_2-t2v_turbo`, `gemini_omni`, `gemini_flash` — are paywalled. Even when `plan_type` says `"plus"`, the backend may still enforce trial restrictions; the `error_type` in the response is authoritative.

**Checking credits**: `higgsfield workspace list --json` shows `credits`. After each generation, re-check — `cinematic_studio_3_0` costs ~80 credits per 8s video.

## OAuth Renewal via CLI (most reliable)

When the MCP transport is down or tokens are expired, the **CLI-based OAuth flow with SSH tunnel** is the most reliable method:

1. Start `higgsfield auth login` on the VPS — it prints an OAuth URL and listens on `localhost:8766`
2. Have the user SSH-tunnel from their local machine: `ssh -L 8766:localhost:8766 root@<vps-ip>`
3. User opens the printed URL in browser → Google OAuth → redirects to `localhost:8766/callback` → SSH tunnel routes it to VPS
4. After success, `higgsfield auth token` returns the bearer token usable for direct MCP calls

**Token reuse**: After auth, use the CLI token (`higgsfield auth token`) in MCP `Authorization: Bearer` headers — no need to sync with `mcp-tokens/`.

## Transport & OAuth Pitfalls

The MCP SSE transport can go down silently — the agent gets empty tool results or hangs.

## Cost Estimation

Add `"get_cost":true` to `params` before generating:
```json
{"params":{"model":"kling3_0","prompt":"...","aspect_ratio":"16:9","duration":5,"mode":"std","sound":"off","get_cost":true}}
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "transport is down" | MCP session died | `hermes mcp test higgsfield` |
| "expected object, received undefined" on `generate_video` | Missing `params` wrapper | Wrap args in `{"params":{...}}` |
| "unknown model kling-v1-6" | Wrong model ID | Use `kling3_0` |
| "Something went wrong" on generate | Token expired, server error, or bad params | Check token, simplify prompt, try `get_cost` first |
| "no cached tokens found" | Token expired, can't refresh headless | Run `hermes mcp login higgsfield` interactively |
