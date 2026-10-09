---
name: hermes-model-picker
description: "Customize the Hermes /model picker in the TUI — reorder providers, update curated model lists, sync fallback models, clear stale caches. Use when models don't appear, when the user wants providers reordered, or when adding new provider model catalogs."
version: 1.0.0
author: walter
metadata:
  hermes:
    tags: [hermes, tui, model, picker, provider, customization]
related_skills:
  - hermes-tui-customization
  - hermes-provider-mastery
---

# Hermes Model Picker Customization

The TUI's `/model` picker lets users switch providers and models interactively. Three levers control what appears and in what order.

## Architecture Flow

```
User types /model in TUI
  → tui_gateway/server.py: _cmd_model()
    → hermes_cli/inventory.py: load_picker_context(canonical_order=True)
      → hermes_cli/model_switch.py: list_authenticated_providers()
        → hermes_cli/models.py: curated_models_for_provider()
          → 1. Try provider_model_ids() (live API via providers/base.py fetch_models)
          → 2. If no profile or empty: use _PROVIDER_MODELS (static curated list)
          → 3. If provider in _MODELS_DEV_PREFERRED: merge with models.dev catalog
      → hermes_cli/models.py: _reorder_canonical()
        → Reorders to CANONICAL_PROVIDERS declaration order
    → build_models_payload() → rendered in picker
```

**Key insight**: The TUI picker uses **curated lists** (`_PROVIDER_MODELS`), NOT the live `/v1/models` API. This prevents TTS/embedding/safety models from cluttering the picker.

## Lever 1: Provider Order

**File**: `hermes_cli/models.py` ~line 912, variable `CANONICAL_PROVIDERS`

This `list[ProviderEntry]` controls the display order. When `canonical_order=True` (TUI default), providers sort to match this declaration. Non-canonical providers append alphabetically at the end.

To put most-used providers first:

```python
CANONICAL_PROVIDERS: list[ProviderEntry] = [
    # ── Most-used (top) ──────────────────────────────────
    ProviderEntry("nvidia",     "NVIDIA NIM",     "NVIDIA NIM (free tier, 120+ models)"),
    ProviderEntry("gemini",     "Google AI Studio","Google AI Studio (Gemini 2.5 Pro/Flash, TTS)"),
    ProviderEntry("openrouter", "OpenRouter",      "OpenRouter (200+ models, web fetch)"),
    ProviderEntry("anthropic",  "Anthropic",       "Anthropic (Claude Opus 4.8, Sonnet 4.5)"),
    # ── Rest in default order ────────────────────────────
    ProviderEntry("openai-codex","OpenAI Codex",   "OpenAI Codex (gpt-5.2-codex)"),
    # ...
]
```

**After editing**: `systemctl --user restart hermes-gateway.service`

## Lever 2: Curated Model Lists

**File**: `hermes_cli/models.py` ~line 113, variable `_PROVIDER_MODELS`

```python
_PROVIDER_MODELS = {
    "nvidia": [
        "moonshotai/kimi-k2.6",           # First = default highlight cursor
        "deepseek-ai/deepseek-v4-pro",
        "deepseek-ai/deepseek-v4-flash",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "qwen/qwen3.5-397b-a17b",
        "mistralai/mistral-medium-3.5-128b",
    ],
}
```

**Critical**: First model in list gets the highlight cursor by default. Order by preference.

## Lever 3: Provider Plugin Fallbacks

**File**: `plugins/model-providers/<name>/__init__.py`

Each provider plugin has `fallback_models` — used when live API is unreachable. Keep in sync with `_PROVIDER_MODELS`.

```python
# plugins/model-providers/nvidia/__init__.py
NvidiaProvider = SimpleProvider(
    name="nvidia",
    base_url="https://integrate.api.nvidia.com/v1",
    fallback_models=(
        "moonshotai/kimi-k2.6",
        "deepseek-ai/deepseek-v4-pro",
        # ...
    ),
)
```

## Provider Cleanup Principles

When `/model` contains several entries for one upstream vendor, first classify each entry by endpoint, transport mode, model family, and whether it is direct or proxied.

- Consolidate only entries that use compatible wire protocols. An Anthropic Messages route and an OpenAI/Codex Responses route must remain distinct providers even when the vendor and API key are shared.
- Prefer two clearly capability-labelled entries over several ambiguous vendor-name variants.
- Remove a superseded intermediary only after confirming no workflow still relies on it.
- After scalar or list edits, validate the configuration and parse it back to assert provider IDs, labels, transport modes, and value types.
- Beware list-shaped CLI values: a JSON-looking value such as `["model-id"]` can be persisted as a string rather than a real YAML list. Verify the parsed type instead of trusting visual appearance or a successful setter message.

See `references/provider-cleanup.md` for a compact protocol-aware cleanup example and verification checklist.

### One visible folder, several internal transports

When the user explicitly wants one Desktop folder but the models require incompatible transports, preserve the runtime providers and consolidate **presentation only**:

- Post-process the Desktop `model.options` payload after `build_models_payload()`.
- Match provider rows by `slug` (not `id`); payload model lists are strings, not `{id, name}` objects.
- Keep one visible provider row with the exact requested label, model IDs, and order; hide only the transport-specific rows.
- Before `switch_model()`, map `(visible provider slug, model ID)` to the actual runtime provider for exceptional models.
- Verify both the default payload and `include_unconfigured=True`, because duplicate configured/custom rows can otherwise survive unnoticed.
- Do not claim the live Desktop changed until its gateway has safely reloaded the code. If restarting would terminate unrelated user work, leave processes intact and state that activation occurs on the next restart.

See `references/desktop-presentation-groups.md` for the implementation and verification recipe.

## Cache Management

| File | Purpose | TTL |
|---|---|---|
| `~/.hermes/provider_models_cache.json` | Cached model lists per provider | 1 hour |
| `~/.hermes/models_dev_cache.json` | models.dev API catalog | Session |

### Stale Cache Symptoms
- Models don't appear after adding API key
- Model count doesn't match live API
- Cache timestamp shows `1970-01-01` (epoch 0 = corrupted)

### Fix

```bash
# Nuclear: delete all caches
rm -f ~/.hermes/provider_models_cache.json ~/.hermes/models_dev_cache.json
systemctl --user restart hermes-gateway.service

# Or via CLI
hermes model --refresh   # Wipes cache and re-fetches every provider's /v1/models
```

## Source Locations

| Component | File | Function/Variable |
|---|---|---|
| Provider display order | `hermes_cli/models.py` | `CANONICAL_PROVIDERS` (~912) |
| Curated model lists | `hermes_cli/models.py` | `_PROVIDER_MODELS` (~113) |
| Models.dev preferred | `hermes_cli/models.py` | `_MODELS_DEV_PREFERRED` (~2012) |
| Provider model ID fetch | `hermes_cli/models.py` | `provider_model_ids()` (~2068) |
| Curated + merge logic | `hermes_cli/models.py` | `curated_models_for_provider()` (~1621) |
| Authenticated providers | `hermes_cli/model_switch.py` | `list_authenticated_providers()` (~1176) |
| TUI picker entry | `tui_gateway/server.py` | `_cmd_model()` |
| Picker context builder | `hermes_cli/inventory.py` | `build_models_payload()`, `load_picker_context()` |
| Live fetch base | `providers/base.py` | `fetch_models()` (~155) |
| Provider registry | `providers/__init__.py` | `get_provider_profile()` (~65) |

## Pitfalls

1. **TUI caches model state at startup.** Changes to `_PROVIDER_MODELS` or `CANONICAL_PROVIDERS` require gateway restart + TUI restart.

2. **Live API vs curated list mismatch.** The live API may return 120+ models (including TTS, safety, embeddings). The picker intentionally shows only curated models. Don't try to make the picker show all live models — that's by design.

3. **Cache timestamp corruption.** If `provider_models_cache.json` shows age of ~56 years (494764 hours), the timestamp field is 0 (epoch). Delete and restart.

4. **Provider plugin vs config.yaml.** The plugin's `fallback_models` is separate from `config.yaml` provider entries. Both need updating when adding new models.

5. **`hermes model --refresh` requires interactive TUI.** In non-interactive sessions, delete cache files manually and restart the gateway.

## NVIDIA NIM Models (Free Tier, AA > 46)

As of 2026-06-11, these NVIDIA NIM models score above 46 on AA benchmarks:

| Model | AA Score | Notes |
|---|---|---|
| `moonshotai/kimi-k2.6` | 51 | Frontier reasoning, 1T params |
| `deepseek-ai/deepseek-v4-pro` | 49 | DeepSeek flagship |
| `nvidia/nemotron-3-ultra-550b-a55b` | 47 | 550B params, cold start >90s |
| `deepseek-ai/deepseek-v4-flash` | 47 | Fast variant |
| `qwen/qwen3.5-397b-a17b` | 45.8 | Near threshold |

**API endpoint**: `https://integrate.api.nvidia.com/v1`
**Auth**: Set the NVIDIA API key in your hermes `.env` file.
