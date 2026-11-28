# xAI / Grok Endpoint Verification

Use this reference for questions such as “is this Grok model available in Hermes as a selectable endpoint?”.

## What must be distinguished

| Layer | Meaning | Verification |
|---|---|---|
| Web product | Grok/X UI feature or subscription entitlement | Inspect the original announcement, but do not treat it as API proof |
| Hermes catalog | Model ID known to the `/model` picker | `hermes model --refresh`; inspect the `xai` and `xai-oauth` lists |
| Authentication | Credential path is available | `hermes auth status xai-oauth` or `hermes auth status xai` |
| Inference entitlement | xAI actually permits the request | A minimal real request or the user's first invocation; catalog presence is insufficient |

## Provider paths

- `xai-oauth`: Hermes-managed OAuth/device-code flow, xAI Responses-style transport, no API key in `config.yaml`. Typically requires an eligible SuperGrok or X Premium+ account; xAI may still reject inference with HTTP 403.
- `xai`: direct xAI API-key path, normally `https://api.x.ai/v1` with `XAI_API_KEY`. This is a separate entitlement path from the web application.

Built-in providers can be implemented in Hermes without a matching `providers.<name>` block in the user's `config.yaml`. Therefore, “not present under `providers:`” is not evidence that the endpoint is unavailable.

## Legitimate local endpoint path

Hermes exposes an OpenAI-compatible local proxy for supported OAuth upstreams. For xAI, verify and start it with:

```bash
hermes proxy providers
hermes proxy status
hermes proxy start --provider xai --host 127.0.0.1 --port 8645
```

This reuses Hermes-managed OAuth; it does not extract or export browser cookies/tokens, and it cannot bypass xAI team spending limits or subscription gates. If the upstream returns `HTTP 402 personal-team-blocked:spending-limit`, the same entitlement failure should be expected through the proxy.

## Evidence pattern from the Hermes picker

The xAI curated catalog can contain IDs such as `grok-build-0.1`, `grok-4.5`, and other current xAI models. These IDs are dynamic and must be rechecked after a catalog refresh; do not hard-code a model list in a user answer.

## Answering rule

When the picker contains the exact requested ID, answer “selectable/catalog-supported”, not “guaranteed usable”. State the provider path and the entitlement caveat. Never silently map a requested Grok ID to another Grok model; if it is absent, report the absence and offer only explicitly verified alternatives.
