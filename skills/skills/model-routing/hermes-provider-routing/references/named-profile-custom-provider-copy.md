# Copy a live named custom provider into an isolated profile

Named Hermes profiles do not inherit the default `providers:` map. A model that works on default can still appear in Desktop `/model` and then fail at agent init:

```
agent init failed: Unknown provider 'kie'. Check 'hermes model' for available providers, or run 'hermes doctor' to diagnose config issues.
```

`kie` is not in `CANONICAL_PROVIDERS`. It only exists as a user-config slug. `resolve_provider_full("kie")` returns None unless that profile's `config.yaml` declares `providers.kie`.

## Do this

1. Read the **working session** identity, not a guessed sibling:
   - `model.provider` (often `custom:kie` even when the session banner says `Provider: custom`)
   - the matching `providers.<slug>` block in the working config
   - `key_env` and whether the target profile `.env` already has that var (presence only; never print the key)
2. Copy that **exact** block into the target profile `config.yaml`.
3. Leave `model.default` / `model.provider` unchanged unless asked to switch the orchestrator. Selectability ≠ default.
4. Verify with `HERMES_HOME` pointed at the profile:

```python
resolve_provider_full("kie", cfg["providers"], None)  # must not be None
resolve_runtime_provider(
    requested="custom",
    explicit_base_url="https://api.kie.ai/claude",
    target_model="grok-4-6",
)
# → base_url https://api.kie.ai/grok/v1, api_mode codex_responses
```

## Do not do this

- Invent `kie-grok`, `kie-claude`, or another transport slug because Grok needs `/grok/v1`. Runtime routing on the live `kie` block already rewrites `grok-*`.
- Put `grok-4-6` on `kie-gpt` (`https://api.kie.ai/codex/v1`). That is the GPT/Luna/Sol family, not Grok.
- Treat a `PROVIDER_GROUPS` key named `kie` as a real provider. Groups are picker display only; init still needs `providers.kie` in the profile config.
- Stop after the diagnosis when the user asked to make the current model usable on the profile.

## Live Kie identity (default / this class)

```yaml
providers:
  kie:
    api: https://api.kie.ai/claude
    api_mode: anthropic_messages
    default_model: claude-opus-4-8
    key_env: KIE_API_KEY
    models: [claude-opus-5, claude-opus-4-8, claude-opus-4-7, claude-opus-4-6,
             claude-sonnet-5, claude-fable-5, gemini-3.1-pro, gemini-3-5-flash,
             grok-4-6]
    name: Kie.ai — Claude / Gemini / Grok
    extra_headers: '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"}'
```

`kie-gpt` can coexist. It is a second provider, not a substitute for `kie`.
