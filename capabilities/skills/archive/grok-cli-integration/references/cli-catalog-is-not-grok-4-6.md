# Grok CLI catalog is not Grok 4.6

When Hermes uses the local OpenAI-compatible Grok CLI proxy, list models without printing `~/.grok/auth.json`:

```text
GET http://127.0.0.1:8766/v1/models
```

Measured 2026-08-19: `{"data":[{"id":"grok-4.5",...}]}` only. That subscription OAuth path is **grok-4.5**, not grok-4-6.

If the user asked for Grok 4.6:

- keep Kie `providers.kie` / model `grok-4-6` (runtime `https://api.kie.ai/grok/v1`);
- offer CLI 4.5 as a labeled cheaper/free alternative, never a silent substitute;
- isolated profiles do not inherit default `providers:` — copy `providers.grok-cli` separately if they want it selectable.

See also `kie-ai-provider-mastery` / `references/grok-4-6-kie-cost-and-cache.md`.
