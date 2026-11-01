# Kie.ai Provider Group & Pricing

## Overview
Kie.ai splits its models across multiple provider entries:
- `kie-claude` — Claude Opus/Sonnet/Haiku via Anthropic Messages API
- `kie-gemini-pro` — Gemini 3.1 Pro
- `kie-gemini-flash` — Gemini 3.5 Flash

## 1. Provider Group in Model Picker

Added to `PROVIDER_GROUPS` in `hermes_cli/models.py`:

```python
"kie": ("Kie.ai", "Claude, Gemini & GPT models via Kie.ai gateway",
        ["kie-claude", "kie-gemini-pro", "kie-gemini-flash"]),
```

**Appears in all pickers:**
- CLI `/model` (prompt_toolkit modal): `▸ Kie.ai (3 providers)` → expand/collapse
- Telegram `/model` inline keyboard
- Setup wizard & Dashboard picker

## 2. Pricing Support

Added `_fetch_kie_pricing()` in `hermes_cli/models.py` (hardcoded — Kie.ai doesn't expose `/v1/models` with pricing):

```python
def _fetch_kie_pricing(*, force_refresh: bool = False) -> dict:
    return {
        "claude-opus-4-6":       {"prompt": "0.00000625", "completion": "0.00003125"},  # 0.25 cr
        "claude-sonnet-4-6":     {"prompt": "0.00000625", "completion": "0.00003125"},
        "claude-haiku-4-5":      {"prompt": "0.00000625", "completion": "0.00003125"},
        "claude-opus-4-7":       {"prompt": "0.00000625", "completion": "0.00003125"},
        "claude-opus-4-8":       {"prompt": "0.00000625", "completion": "0.00003125"},
        # Aliases for provider model IDs
        "claude-opus-4-5":       {"prompt": "0.00000625", "completion": "0.00003125"},
        "gemini-3-5-flash":      {"prompt": "0.00000025", "completion": "0.000001"},   # 0.01 cr
        "gemini-3.1-pro":        {"prompt": "0.000675", "completion": "0.0027"},       # 27 cr
        "gemini-3-5-flash-openai": {"prompt": "0.00000025", "completion": "0.000001"},
        "gpt-5-4":               {"prompt": "0.000012", "completion": "0.00006"},      # 0.48 cr
        "gpt-5-5":               {"prompt": "0.000012", "completion": "0.00006"},
    }
```

Wired in `get_pricing_for_provider()`:
```python
if normalized.startswith("kie-"):
    return _fetch_kie_pricing(force_refresh=force_refresh)
```

**Result in pickers:**
- $6.25 / $31.25 per Mtok for Claude models (0.25 credits)
- $675 / $2,700 per Mtok for Gemini 3.1 Pro (27 credits)
- $0.25 / $1.00 per Mtok for Gemini 3.5 Flash (0.01 credits)
- $12 / $60 per Mtok for GPT-5 variants (0.48 credits)

(1 Kie.ai credit ≈ $0.005 estimated)

## 3. Files Modified

| File | Changes |
|------|---------|
| `hermes_cli/models.py` | `PROVIDER_GROUPS` entry + `_fetch_kie_pricing()` + wiring |
| `cli.py` | Group expand/collapse in `_open_model_picker()`, `_get_model_picker_display()`, `_handle_model_picker_selection()`, `_rebuild_grouped_providers()` |
| `tests/hermes_cli/test_provider_groups.py` | Added `custom_provider_groups = {"kie"}` to allowlist test |

## 4. Pitfalls

1. **Group member slugs must match `providers` section keys exactly** in `config.yaml`
2. **Custom slugs not in `CANONICAL_PROVIDERS`** → test needs `custom_provider_groups` allowlist
3. **Pricing formatter rejects "per_gen"** — only include token-based chat models
4. **Model ID aliases needed** — provider lists may use different IDs than Kie.ai docs
5. **Source patches overwritten by `hermes update`** — re-apply or track in local branch