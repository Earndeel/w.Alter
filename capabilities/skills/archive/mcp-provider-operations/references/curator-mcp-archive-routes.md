# Archived MCP provider routing

Confirm the real archive location with `skill_view(name='.archive/<name>')` before loading a historical recipe. Use the original `file_path` from the archive result and never retry an old unqualified name.

- `.archive/hosted-mcp-oauth/SKILL.md` — native hosted-MCP OAuth on headless/SSH Hermes.
  - `.archive/hosted-mcp-oauth/references/higgsfield-mcp-oauth.md` — redirect, timeout, stale-client, and PTY recipe.
  - `.archive/hosted-mcp-oauth/references/higgsfield-model-catalog.md` — model discovery and async generation schema.
  - `.archive/hosted-mcp-oauth/scripts/higgsfield_fifo_auth.py` — FIFO callback implementation.
- `.archive/mcp-oauth-troubleshooting/SKILL.md` — OAuth callback, Tailscale, PKCE, and timeout diagnostics.
  - `.archive/mcp-oauth-troubleshooting/references/tailscale-oauth-bypass.md` — direct callback decision and provider restriction.
  - `.archive/mcp-oauth-troubleshooting/references/higgsfield-oauth-headless.md` — localhost configuration and verification.
  - `.archive/mcp-oauth-troubleshooting/scripts/oauth-tailscale-callback.py` — direct callback implementation.
  - `.archive/mcp-oauth-troubleshooting/scripts/oauth-fifo-callback.py` — paste/FIFO callback implementation.
- `.archive/remote-mcp-provider-onboarding/SKILL.md` — secret placement, schema discovery, and provider verification.
  - `.archive/remote-mcp-provider-onboarding/references/serpapi-mcp.md` — path-authenticated SerpAPI wrapper contract.
