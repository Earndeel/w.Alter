# Kie.ai Gemini Endpoint Discovery (2026-06-02)

## Endpoint Pattern

Each Gemini model has its OWN endpoint: `POST https://api.kie.ai/{model-name}/v1/chat/completions`

Shared endpoints do NOT work:
- `/openai/v1/chat/completions` -> 422 for all Gemini models
- `/gemini/v1/chat/completions` -> 422 for all Gemini models

## Verified Model URLs

| Model | URL path (after base) | Body `model` field |
|-------|----------------------|-------------------|
| Gemini 3.5 Flash | `gemini-3-5-flash-openai` | `gemini-3-5-flash` |
| Gemini 3.1 Pro | `gemini-3.1-pro` | `gemini-3.1-pro` |
| Gemini 3 Flash | `gemini-3-flash` | `gemini-3-flash` |
| Gemini 2.5 Flash | `gemini-2.5-flash` | `gemini-2.5-flash` |

## Naming Quirks

- **3.5 Flash:** URL MUST be `gemini-3-5-flash-openai` (hyphens + `-openai`). `gemini-3.5-flash` or `gemini-3-5-flash` in URL -> 422.
- **3.1 Pro:** URL MUST use dots `gemini-3.1-pro`. Hyphens `gemini-3-1-pro` -> 422.

## Capabilities Verified (2026-06-02)

- Text: OK, 0.01 credits
- Image input (base64): OK, 0.11 credits for tiny PNG
- Multi-turn: OK
- Streaming SSE: OK
- Prompt caching: NOT available (no `cached_tokens`, no reduction on repeated prompts)

## Hermes Config

```yaml
providers:
  kie-gemini-pro:
    api: https://api.kie.ai/gemini-3.1-pro
    api_mode: chat_completions
    default_model: gemini-3.1-pro
    key_env: KIE_API_KEY
    models: [gemini-3.1-pro]
  kie-gemini-flash:
    api: https://api.kie.ai/gemini-3-5-flash-openai
    api_mode: chat_completions
    default_model: gemini-3-5-flash
    key_env: KIE_API_KEY
    models: [gemini-3-5-flash]
```

Requires `hermes-custom-provider-validation` patch to avoid /model warning.
