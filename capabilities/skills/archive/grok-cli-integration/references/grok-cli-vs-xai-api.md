# Verified investigation notes

## Host and billing separation

- Hermes' xAI OAuth path resolves to `https://api.x.ai/v1` and can return `402 personal-team-blocked` when the API billing account/spending limit is unavailable.
- Grok Build CLI uses a separate service host, `https://cli-chat-proxy.grok.com/v1`.
- An unauthenticated `GET /v1/models` probe to the CLI host returned HTTP 401 with `auth_kind=none` and `no auth context`. This proves the route exists and requires CLI credentials; it does not prove account entitlement.
- The public web UI, direct API, and CLI subscription path must be tested independently.

## CLI path

The official CLI guidance uses `grok login` and stores CLI auth separately from Hermes, currently under `~/.grok/auth.json`. The preferred integration is a headless CLI worker (`grok --no-auto-update -p ...`) rather than pretending the subscription proxy is the direct xAI API.

## Adapter decision

If Hermes must expose Grok as a model provider, use a localhost-only adapter or a CLI/ACP bridge. Do not repoint Hermes' existing `xai-oauth` provider at the CLI proxy: Hermes validates OAuth inference origins against `api.x.ai` / `*.x.ai`, while the CLI proxy is on `grok.com`. Never extract browser cookies or log CLI bearer credentials.

## Entitlement

A free or paid web session is not sufficient evidence for CLI entitlement. The only reliable check is `grok login` followed by a minimal authenticated smoke test; run this before changing Hermes configuration.
