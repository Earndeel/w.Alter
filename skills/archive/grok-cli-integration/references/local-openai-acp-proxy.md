# Local OpenAI-compatible proxy backed by Grok CLI ACP

Use this pattern when the requested UX is “select `grok-4.5` like an ordinary Hermes API model,” while authentication must remain the Grok CLI subscription/OAuth session.

## Verified flow

```text
Hermes chat_completions provider
  -> http://127.0.0.1:<free-port>/v1/chat/completions
  -> local adapter
  -> grok agent -m grok-4.5 stdio (ACP JSON-RPC)
  -> Grok subscription/OAuth
```

A direct ACP client probe returned the requested literal output, and a subsequent real Hermes invocation through the localhost OpenAI facade also returned the requested literal output. This is the acceptance boundary: **the final Hermes command**, not merely ACP initialization.

## Durable implementation rules

1. Bind to `127.0.0.1`, never `0.0.0.0`.
2. Before selecting a port, inspect listeners; if occupied, choose another port rather than killing an unrelated process.
3. Spawn Grok with process-scoped removal of `XAI_API_KEY` and `XAI_BASE_URL`, preserving the user's global environment.
4. Present at minimum:
   - `GET /health`
   - `GET /v1/models`
   - `POST /v1/chat/completions`
5. Convert ACP response content, finish reason, and tool calls into OpenAI chat-completion shape. If `stream=true` is advertised, return valid SSE ending in `data: [DONE]`; do not claim token streaming if the adapter buffers the full ACP response.
6. Give model calls a long timeout (for example 900 seconds); coding-agent transports can exceed ordinary HTTP defaults.
7. Register the custom Hermes provider through supported CLI configuration commands rather than direct writes to protected config:

```bash
hermes config set providers.grok-cli.api http://127.0.0.1:<port>/v1
hermes config set providers.grok-cli.api_mode chat_completions
hermes config set providers.grok-cli.default_model grok-4.5
hermes config set providers.grok-cli.models '["grok-4.5"]'
hermes config set providers.grok-cli.request_timeout_seconds 900
hermes config set providers.grok-cli.stale_timeout_seconds 900
```

8. Verify end to end:

```bash
hermes chat --provider grok-cli -m grok-4.5 \
  -q 'Reply exactly: HERMES_GROK_OK' -Q --max-turns 1
```

Do not report completion unless stdout contains the requested literal and the command exits successfully.

## Service lifecycle

For reboot persistence, install the adapter as a supervised service with restart-on-failure. If an ad-hoc proxy is already serving the chosen port during installation, enable the service for reboot but do not start a conflicting second instance. Never use broad `pkill` cleanup.

## Architectural pitfall

Do not begin by spreading Grok-specific dispatch through Hermes core when a local standards-compatible boundary satisfies the user. Native ACP integration is justified only for ACP-specific semantics. The proxy architecture is smaller, reversible, and keeps subscription credentials under the official CLI's control.
