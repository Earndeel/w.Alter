---
name: mcp-provider-operations
description: Use when onboarding or debugging remote MCP providers.
tags: [mcp, oauth, http, providers, headless, schema]
metadata:
  hermes:
    tags: [mcp, oauth, http, providers, headless, schema]
---

# Remote MCP Provider Operations

Use this umbrella for hosted HTTP/streamable MCP onboarding, OAuth on headless Hermes hosts, path-authenticated providers, schema discovery, and safe verification.

## Contract discovery

Start from the provider's official MCP documentation and live tool schema. Keep endpoint authentication modes distinct: OAuth, header token, and credential-in-URL path are not interchangeable. Treat a URL containing a secret as a secret-bearing configuration and keep the raw value out of YAML, logs, commands, and reports.

Inspect `initialize`, session behavior, `tools/list`, and nested argument schemas before calling a tool. Providers may be stateless, may omit `MCP-Session-Id`, or may wrap arguments under `mode` and `params`; never copy a provider example into a wrapper without checking the live schema.

## Headless OAuth workflow

Prefer Hermes native OAuth for persistent connections. Use a real or pseudo-TTY, long human-login/connect timeouts, and a consistent `localhost` redirect when the provider allows only localhost. Give the user the newest authorization URL, accept the final callback URL on the waiting host, and never reuse a URL after a failed attempt because state and PKCE rotate. Remove stale dynamic client/token files when redirect metadata changes, then verify with `hermes mcp test`, reload MCP, and start a fresh session if needed.

A Tailscale callback can avoid paste-back only when the provider accepts the non-localhost redirect and the callback port is reachable; otherwise use the localhost paste flow. Keep PKCE state bound to the current login and store tokens in Hermes' standard token location.

## Safe onboarding and verification

Resolve credentials through the configured secret source, select only required tools, and issue one minimal non-sensitive call after discovery. Distinguish endpoint discovery, authentication, schema compatibility, tool success, and session reload. A successful `initialize` is not proof that the requested tool works.

## Failure handling

Classify invalid scopes, redirect mismatch, stale state, timeout, provider rejection, schema error, and transport failure separately. Fix the layer evidenced by the failure instead of changing scopes or auth modes blindly.

Exact provider OAuth, callback scripts, model-catalog, path-auth, and schema recipes are routed in `references/curator-mcp-archive-routes.md`.
