---
name: delegate-task-per-model
description: "Route delegate_task subagents to different models per-task. Override model/provider for individual tasks in a batch delegation."
triggers:
  - delegate task model
  - per-task model
  - subagent model override
  - delegation model routing
metadata:
  hermes:
    tags: [delegate_task, model-routing, delegation, subagent]
    related_skills: [hermes-delegate-task-routing]
---

# Delegate Task — Per-Task Model Override

Route individual tasks in a `delegate_task` batch to different models. Useful when one task needs a creative model (writing) and another needs a reasoning model (code analysis).

## Usage

```json
delegate_task(tasks=[
  {"goal": "Quick task", "toolsets": ["web"]},
  {"goal": "Creative writing", "model": {"provider": "openrouter", "model": "anthropic/claude-sonnet-4"}, "toolsets": ["web"]},
  {"goal": "Code analysis", "model": {"provider": "openrouter", "model": "openai/o3"}, "toolsets": ["terminal", "file"]}
])
```

- Task 0: uses global `delegation.model` from config.yaml
- Task 1: routes to Claude Sonnet via OpenRouter
- Task 2: routes to o3 via OpenRouter

## Schema

Each task item supports an optional `model` object:
- `model.provider` (optional): Provider name (e.g. `openrouter`, `anthropic`). If omitted, inherits current provider.
- `model.model` (required): Model name (e.g. `anthropic/claude-sonnet-4`)

## Implementation (delegate_tool.py)

### 1. Schema addition (line ~2774 in DELEGATE_TASK_SCHEMA)

Added `model` property to task items:
```python
"model": {
    "type": "object",
    "properties": {
        "provider": {"type": "string"},
        "model": {"type": "string"},
    },
    "required": ["model"],
}
```

### 2. Task loop credential resolution (line ~2060)

```python
task_model_cfg = t.get("model") or {}
if task_model_cfg and isinstance(task_model_cfg, dict) and (
    task_model_cfg.get("model") or task_model_cfg.get("provider")
):
    synthetic_cfg = dict(cfg)
    if task_model_cfg.get("model"):
        synthetic_cfg["model"] = task_model_cfg["model"]
    if task_model_cfg.get("provider"):
        synthetic_cfg["provider"] = task_model_cfg["provider"]
        synthetic_cfg.pop("base_url", None)  # CRITICAL
    task_creds = _resolve_delegation_credentials(synthetic_cfg, parent_agent)
else:
    task_creds = creds
```

### 3. _load_config() fix (line ~2459)

YAML first, CLI overlay only if non-empty:
```python
def _load_config() -> dict:
    merged = {}
    try:
        from hermes_cli.config import load_config
        full = load_config()
        merged = dict(full.get("delegation") or {})
    except Exception:
        pass
    try:
        from cli import CLI_CONFIG
        cli_cfg = CLI_CONFIG.get("delegation") or {}
        if cli_cfg:
            for k, v in cli_cfg.items():
                if v and v != "":
                    merged[k] = v
    except Exception:
        pass
    return merged
```

## Critical Pitfall: base_url Clearing

When global config has `base_url` set (e.g. xiaomi endpoint), `_resolve_delegation_credentials()` checks `configured_base_url` FIRST and returns `provider: "custom"` with that base_url — completely ignoring the provider override.

**Fix**: `synthetic_cfg.pop("base_url", None)` when overriding the provider. This forces the code to fall through to `resolve_runtime_provider()` which correctly resolves OpenRouter/Anthropic credentials.

## Pitfalls

- **Stale process memory**: TUI slash workers cache Python modules in `sys.modules`. Changes to `delegate_tool.py` are NOT picked up by running processes. `inspect.getsource()` reads from disk (not memory), so it can show new code while the running function uses old code. **Test via cron job** (fresh process).
- **Gateway restart required**: After editing config.yaml or delegate_tool.py, the gateway must be restarted. CLI_CONFIG is loaded at startup and cached.
- **Provider must exist**: `model.provider` must match an actual provider in config.yaml's `providers:` section (e.g. `openrouter`, `gitlawb`), not a friendly name like `xiaomi`.
- **OpenRouter credits**: Large max_tokens (e.g. 65536 for Gemini 2.5 Pro) may exceed available credits. Use cheaper models (e.g. `google/gemini-2.5-flash`) or add credits.
- **Silent fallback**: If per-task resolution fails, falls back to global config silently. Always verify the result JSON `model` field matches expectations.
