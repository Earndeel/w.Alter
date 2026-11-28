# OpenAI-compatible proxy vs native ACP provider

## Decision rule

Use a localhost OpenAI-compatible proxy when the desired user experience is selecting Grok in Hermes exactly like an ordinary API model. Use native ACP only when agent-protocol capabilities are explicitly required.

## Why the proxy is the safer default

- Reuses Hermes' existing custom OpenAI endpoint path instead of changing provider registries, auth dispatch, runtime clients, auxiliary clients, and pickers.
- Keeps Grok OAuth inside the official CLI credential store.
- Makes rollback and upgrades independent from Hermes core.
- Matches the user's mental model: provider + model, not autonomous coding worker.

## Minimum adapter contract

Expose only what Hermes needs:

- `GET /v1/models` containing exact model ID `grok-4.5`.
- `POST /v1/chat/completions` with OpenAI-style messages.
- Non-streaming response first; advertise streaming only after SSE is verified.
- Bounded timeout, cancellation/child cleanup, structured upstream errors.
- Bind to `127.0.0.1`; never expose the credential-bearing bridge publicly.
- Spawn Grok with process-scoped environment removal: `env -u XAI_API_KEY -u XAI_BASE_URL ...`.

## Acceptance checklist

1. Direct OAuth smoke test confirms the CLI banner/path uses `grok.com`, not `XAI_API_KEY`.
2. Proxy health/model endpoint reports `grok-4.5`.
3. Direct proxy chat request returns the expected text.
4. Hermes custom-provider configuration selects the proxy and exact model.
5. A real `hermes chat` request succeeds through that provider.
6. Picker/catalog visibility is verified if the user requested GUI/TUI selection.
7. Restart persistence is tested without editing unrelated Hermes source.

An ACP `initialize` success proves protocol/auth reachability only. It does not prove ordinary Hermes model use, response translation, or picker integration.

## Failure pattern to avoid

Do not treat “must appear like any API model” as permission to generalize an existing ACP client throughout Hermes core. That approach expands the blast radius before validating the simplest architecture and can yield many passing transport assumptions while the actual requested UX remains unavailable.
