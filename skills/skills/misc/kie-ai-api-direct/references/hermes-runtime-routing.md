# Hermes runtime routing notes for Kie.ai

Validated from a Hermes runtime debugging session on 2026-06-18.

## Symptom

`hermes chat --provider kie --model claude-opus-4-8 ...` returns a plausible answer, but the Kie.ai dashboard/logs show no call.

## Root cause pattern

Hermes may have failed on the primary Kie route and then used the global fallback chain. The visible response can therefore come from another provider while the CLI command still displays the requested model name.

Do not trust the prompt response alone. Verify the persisted session billing metadata in `state.db`:

- `sessions.billing_provider`
- `sessions.billing_base_url`
- `sessions.model`
- `sessions.model_config`

Expected for a real Kie runtime call:

- `billing_provider`: `custom`
- `billing_base_url`: `https://api.kie.ai/claude`
- `model`: requested Kie model, e.g. `claude-opus-4-8`

If `billing_provider` is another provider such as `nvidia`, the response did not come from Kie even if the command used `--provider kie`.

## Runtime integration details

Kie's Anthropic-compatible runtime needs:

- base URL in Hermes provider config: `https://api.kie.ai/claude`
- API mode: `anthropic_messages`
- request path produced by Anthropic client: `/v1/messages`
- auth header: `Authorization: Bearer <token>`
- browser-like `User-Agent`

A direct curl target remains `https://api.kie.ai/claude/v1/messages`.

## Strict provider tests

For provider smoke tests, disable fallback or ensure the Hermes CLI treats an explicit `--provider kie` as strict. Otherwise a failed Kie call can silently succeed through a fallback provider, leaving no Kie.ai dashboard entry.

Useful verification sequence:

1. Run a unique exact-response prompt through `hermes chat --provider kie --model <model> -Q`.
2. Read the resulting `session_id` from stdout.
3. Inspect `state.db` for that session's `billing_provider` and `billing_base_url`.
4. Only call it a Kie success if billing metadata points to Kie.

## Pitfall

`Error: Your request was blocked` with no Kie dashboard entry often means the request was blocked before useful provider logging, commonly because the Anthropic client path sent incompatible auth or headers. Direct curl with Bearer auth + UA isolates provider reachability from Hermes runtime wiring.
