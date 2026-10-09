---
name: xitter
description: "DEPRECATED — use xurl instead. Fallback X/Twitter via x-cli only if xurl is not installable."
version: 1.1.0
author: Siddharth Balyan + Hermes Agent
license: MIT
platforms: [linux, macos]
prerequisites:
  commands: [uv]
  env_vars: [X_API_KEY, X_API_SECRET, X_BEARER_TOKEN, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET]
metadata:
  hermes:
    tags: [twitter, x, social-media, x-cli]
    homepage: https://github.com/Infatoshi/x-cli
---

## When to Use

- User asks to post, search, or interact with X/Twitter AND `xurl` is not installable
- Fallback only — always try `xurl` skill first

## Pitfalls

- This skill is DEPRECATED — `xurl` is preferred (OAuth 2.0, broader API, maintained)
- Requires 5 X API env vars: `X_API_KEY`, `X_API_SECRET`, `X_BEARER_TOKEN`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`
- `x-cli` installed via `uv tool install` may conflict with other Python tools

# Xitter — DEPRECATED, prefer `xurl`

**This skill is deprecated.** Use the `xurl` skill instead — it is maintained by the X developer platform team, supports OAuth 2.0 PKCE with auto-refresh, and covers a larger API surface.

Fall back to `x-cli` (this skill) only if `xurl` cannot be installed on the target system.

## User Handle Awareness

When the user says "mon twitter", "mon compte X", "checker mon profil", they mean **their own account** — not a general X search. Before doing anything:

1. Check memory for the user's X handle
2. If missing, ask immediately and save it to memory
3. Never waste turns searching session history for a handle that was never stored

## Install (fallback only)

Install upstream `x-cli` with `uv`:

```bash
uv tool install git+https://github.com/Infatoshi/x-cli.git
```

## Quick Commands

```bash
x-cli user get <handle>
x-cli tweet search "query" --max 20
x-cli me mentions --max 20
x-cli me bookmarks --max 20
```

## Cross-References

- **xurl skill** (`social-media/xurl`): Preferred X CLI. Same capabilities, broader API, OAuth 2.0.
- **x_search tool**: Read-only X search via Grok (no X API credits needed). Requires SuperGrok OAuth or XAI_API_KEY.
- **Ecosystem overview**: `xurl/references/x-ecosystem-overview.md` for complete comparison and pricing.
