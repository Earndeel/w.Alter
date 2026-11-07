---
name: hermes-custom-provider-validation
description: Fix Hermes /model validation warning for custom providers that don't expose /v1/models (Kie.ai Gemini, etc.)
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [hermes, validation, custom-provider, kie, gemini]
---

# Hermes Custom Provider /model Validation Fix

## Problem

When using custom providers (e.g. `kie-gemini-flash`) with `api_mode: chat_completions`, the `/model` command shows:

```
Note: could not reach the kie-gemini-flash API to validate `gemini-3-5-flash`. If the service isn't down, this model may not be valid.
```

The model works fine — it's just a validation false alarm.

## Root Cause

`validate_requested_model()` in `hermes_cli/models.py` probes `{base_url}/v1/models` to verify the model exists. Custom providers that don't expose `/v1/models` (Kie.ai per-model URLs, some proxied endpoints) return 404, causing the warning.

The function has special-case handling for `anthropic_messages` mode (accepts without probing) and known providers (`openai-codex`, `minimax`), but generic `chat_completions` custom providers fall through to the warning.

## Fix

Patch `hermes_cli/models.py` at ~line 3667 (after the `anthropic_messages` block, before the generic `fetch_api_models` probe):

```python
    # Check if the model is in the provider's configured models list
    # (for custom providers that don't expose /v1/models, e.g. Kie.ai Gemini)
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        prov_cfg = (cfg.get("providers") or {}).get(normalized) or {}
        cfg_models = prov_cfg.get("models") or []
        if isinstance(cfg_models, list) and requested_for_lookup in cfg_models:
            return {
                "accepted": True,
                "persist": True,
                "recognized": True,
                "message": None,
            }
    except Exception:
        pass
```

## Pitfalls

1. **Import name is `load_config`, NOT `load_cli_config`** — `load_cli_config` does not exist. Using the wrong name silently fails inside `try/except`, making the patch appear to have no effect. Verify: `python3 -c "from hermes_cli.config import load_config"`

2. **Gateway restart required** — The gateway caches Python modules at startup. Run `hermes gateway restart` after patching.

3. **Patch overwritten by `hermes update`** — Re-apply after updates until upstream fixes this. Check if the patch is still present: `grep -n "load_config" hermes_cli/models.py | grep providers`

4. **Config models must be a YAML list** — If `models` was set via `hermes config set providers.X.models '["model"]'`, it may be stored as a string `'["model"]'` instead of a list. Fix: edit config.yaml directly or use Python to load/save.
