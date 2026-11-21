# Coding-provider protocol contracts

Use this reference for provider-specific transport facts when delegating to an external coding CLI. Re-check live provider documentation and the resolved binary before relying on a model list, price, quota, or endpoint.

## OpenCode-compatible routes

- Treat the model ID and API mode as a pair; OpenAI-compatible models use `/v1/chat/completions`, while designated Qwen/MiniMax routes use Anthropic `/v1/messages`.
- Resolve the exact model from the live provider catalog; examples such as `opencode-go/qwen3.7-max` and `opencode-go/kimi-k2.6` are format examples, not a current catalog.
- Keep the base URL's version segment consistent with the selected SDK. If the client already appends `/v1`, remove a duplicate `/v1` from the configured base URL rather than changing the model ID.
- Send the provider's required API-key header only. If an Anthropic-compatible gateway rejects a request because the SDK emits both `x-api-key` and `Authorization: Bearer`, isolate the child client and remove the incompatible header; do not rotate a credential that a direct probe accepts.
- Re-fetch subscription prices, quotas, limits, and availability before making a cost claim, because these values change independently of the CLI version.

## Verification

1. Print the resolved binary and version from the same Hermes environment that will launch the worker.
2. Verify auth with the provider's own status/list command without exposing the secret.
3. Run one bounded smoke request through the exact selected protocol.
4. Inspect request path, headers, response schema, model identity, usage, and cost metadata before treating the route as usable.
5. Keep protocol failures separate from model-quality failures; a format mismatch is not evidence of invalid credentials.
