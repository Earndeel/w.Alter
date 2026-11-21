---
name: hermes-delegate-task-routing
category: devops
description: Route delegate_task subagents to a different provider:model by patching config.yaml and delegate_tool.py. Solves the silent config loading bug.
tags: [hermes, delegate_task, subagent, model-routing, config]
---

# Hermes delegate_task Model Routing

## Problem

The `delegate_task` tool schema does NOT expose `model` or `provider` parameters to the LLM agent. Subagents silently inherit the parent model. However, the **backend code** (`tools/delegate_tool.py`) does support credential overrides via `delegation.model` and `delegation.provider` in `~/.hermes/config.yaml`.

## Bug: Why config.yaml Was Ignored

`_load_config()` in `delegate_tool.py` has this flow:

```python
def _load_config() -> dict:
    from cli import CLI_CONFIG
    cfg = CLI_CONFIG.get("delegation", {})
    if cfg:
        return cfg  # <-- Returns even if model/provider are empty strings!
    from hermes_cli.config import load_config
    return load_config().get("delegation", {})
```

CLI_CONFIG always contains `delegation` with empty `model: ""` and `provider: ""`. So the YAML file is **never read**.

## Fix: Three Changes Required (config + code + environment)

### 1. Set delegation model in config.yaml

```yaml
delegation:
  model: 'google/gemini-3-flash-preview'  # or any model
  provider: openrouter                     # provider for credential resolution
  base_url: ''
  api_key: ''
  max_iterations: 50
  default_toolsets:
  - terminal
  - file
  - web
```

### 2. Patch _load_config() in delegate_tool.py

File: `~/.hermes/hermes-agent/tools/delegate_tool.py`, function `_load_config()` (around line 672):

**Before:**
```python
def _load_config() -> dict:
    try:
        from cli import CLI_CONFIG
        cfg = CLI_CONFIG.get("delegation", {})
        if cfg:
            return cfg
    except Exception:
        pass
    try:
        from hermes_cli.config import load_config
        full = load_config()
        return full.get("delegation", {})
    except Exception:
        return {}
```

**After:**
```python
def _load_config() -> dict:
    merged = {}
    # Layer 1: persistent config from YAML (user overrides)
    try:
        from hermes_cli.config import load_config
        full = load_config()
        merged = full.get("delegation", {})
    except Exception:
        pass
    # Layer 2: CLI runtime config overrides YAML for non-empty values
    try:
        from cli import CLI_CONFIG
        cli_cfg = CLI_CONFIG.get("delegation", {})
        if cli_cfg:
            for k, v in cli_cfg.items():
                if v and v != "":  # Only override if CLI value is non-empty
                    merged[k] = v
    except Exception:
        pass
    return merged
```

## How It Works After Patch

1. `config.yaml` `delegation.model` is read first
2. CLI empty defaults are ignored (empty string check)
3. `_resolve_delegation_credentials()` resolves the full bundle via `hermes_cli.runtime_provider.resolve_runtime_provider()`
4. `_build_child_agent()` passes `model=creds["model"]` to `AIAgent()` — line 201 of delegate_tool.py
5. Subagent runs with the configured model, independent of parent

## Verification

After patching, restart the gateway (kill old PID, start new). Then test with any `delegate_task` call. The result JSON includes `"model": "<model_name>"` per task — verify it matches the configured model.

## Diagnosing: Subagent Still Uses Parent Model After Patch

If you set `delegation.model/provider` in config.yaml, patched `_load_config()`, restarted the gateway, and subagents STILL run on the parent model (check result JSON `model` field), diagnose this chain:

### Step 1: Verify _load_config() returns delegation model
```python
# From the gateway venv:
import sys; sys.path.insert(0, '/root/.hermes/hermes-agent')
from tools.delegate_tool import _load_config
print(_load_config())
# Should show: {'model': 'google/gemini-3-flash-preview', 'provider': 'openrouter', ...}
```

### Step 2: Verify runtime provider resolves with API key
```python
from hermes_cli.config import load_config
cfg = load_config().get('delegation', {})
from hermes_cli.runtime_provider import resolve_runtime_provider
runtime = resolve_runtime_provider(requested=cfg['provider'])
print(f"API key present: {bool(runtime.get('api_key', ''))}")
```

If `api_key` is empty, `resolve_runtime_provider` cannot find the credential. The root cause is often: **`OPENROUTER_API_KEY` is set in `~/.hermes/.env` but NOT exported to the subprocess environment.** The gateway reads `.env` at startup, but if the gateway process doesn't have the key in its environment map, `resolve_runtime_provider` returns `api_key: ''`.

**Fix:** Ensure the gateway process has the API key. Check with:
```bash
cat /proc/<gateway_pid>/environ | tr '\0' '\n' | grep OPENROUTER_API_KEY
```
If empty, the gateway didn't load it. Kill and restart the gateway from a context where `.env` is sourced.

### Step 3: If api_key resolves but model still wrong
The subagent result includes `model` in its output. Cross-check the child agent's `AIAgent(model=...)` call trace — `model=creds["model"]` is passed at line ~19602 of delegate_tool.py. If `creds["model"]` is correct but the child reports a different model, there may be a `providers_ignored` or `providers_allowed` filter blocking your target provider. Check `load_config()` for `providers_ignored` list.

## Scope: What delegation.model Affects

| Mechanism | Uses delegation.model? | Actual model source |
|-----------|----------------------|---------------------|
| `delegate_task` tool | ✅ Yes | `delegation.model` in config.yaml |
| Cron jobs | ❌ No | Session's `model.default` |
| Kanban workers | ❌ No | Profile's own `model.default` |
| Direct `hermes -p <profile> chat` | ❌ No | Profile's config |

**Common mistake:** Changing `delegation.model` thinking it affects cron jobs or Kanban workers. It only affects `delegate_task` calls. Cron jobs use whatever model the session defaults to; Kanban workers use the profile they're spawned with.

## Pitfalls

- **Gateway/TUI MUST be restarted** after editing config.yaml or delegate_tool.py — `CLI_CONFIG` is loaded at startup and cached in memory. Changes to the YAML file are NOT picked up until restart. (Tested 2026-05-24: `CLI_CONFIG` had `provider: gitlawb` from disk but the running TUI still used the old `provider: xiaomi`.)
- `delegation.provider` must match an **actual provider name** defined in `providers:` section of config.yaml (e.g., `gitlawb`, `openrouter`) — NOT a user-friendly name like `xiaomi` or `mimo`. If the provider name doesn't exist, the API key resolves to empty string → `Invalid API Key`. (Tested 2026-05-24: `provider: xiaomi` failed because the actual provider was named `gitlawb`.)
- `delegation.api_key` must be explicitly set if the provider's key resolution doesn't work automatically. Check with: `python3 -c "from hermes_cli.runtime_provider import resolve_runtime_provider; r = resolve_runtime_provider(requested='<provider>'); print(bool(r.get('api_key')))"`
- `delegation.base_url` takes precedence over `delegation.provider` — if you set base_url, provider is ignored
- The `DELEGATE_TASK_SCHEMA` still doesn't show model/provider to the LLM — routing is purely config-driven
- Subagents inherit parent's `providers_allowed`, `providers_ignored`, `providers_order` — if your target provider is blocked, it will fail
- Empty model means "inherit parent model" — only set it if you want an override
- **Silent fallback risk**: If `_resolve_delegation_credentials` returns `api_key: ''` and the ValueError path is somehow bypassed, the child agent may use parent credentials silently. Always verify the result JSON includes the expected model name.
- **API key visibility**: `_resolve_delegation_credentials` delegates to `resolve_runtime_provider()` which reads environment variables. If the gateway was started without `OPENROUTER_API_KEY` in its environment (e.g., no `hermes login` session, or `.env` not loaded into process env), the key will be empty despite existing in `~/.hermes/.env`.
- **Disabling unused toolsets**: Add toolset names to `disabled_toolsets: []` in config.yaml to remove tools from the agent's available set. Example: `disabled_toolsets: ['moa']` disables `mixture_of_agents` (5 API calls per use, slow, expensive). Requires session restart.

## Gemini AI Studio Provider (tested April 2026)

The `gemini` provider in `auth.json` uses `base_url: "https://generativelanguage.googleapis.com/v1beta/openai"` (OpenAI-compatible endpoint). `GEMINI_API_KEY` is in `.env`.

Config for delegation via Gemini:
```yaml
delegation:
  model: gemini-2.5-pro
  provider: gemini
  base_url: https://generativelanguage.googleapis.com/v1beta/openai
```

Model availability on AI Studio:
- `gemini-2.5-pro` — stable, works reliably (~2-3s response)
- `gemini-3.1-pro-preview` — available but times out on generateContent calls

**delegate_task `model` parameter override does NOT work** (tested April 2026). Passing `model={"model":"gemini-2.5-pro","provider":"gemini"}` to delegate_task is ignored — the system always routes through the delegation config (and thus OpenRouter if the config hasn't been patched + gateway restarted). The ONLY way to change delegation routing is: patch `_load_config()` + set config.yaml + restart gateway.

**Reading GEMINI_API_KEY for direct API calls:** The `.env` file CANNOT be `source`d by bash — it contains numbered lines from the Hermes editor that bash interprets as commands. Use Python to read the key.

- **Workaround if delegation routing still fails after patch + restart:** Call the Gemini API directly via urllib instead of going through the subagent system. Successfully used with `gemini-2.5-pro` via `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={key}`.

## Workaround: terminal(background=true) for Parallelization

When `delegate_task` routing is broken (e.g. custom provider with invalid API key, or gateway not restarted), use `terminal(background=True, notify_on_complete=True)` as a parallelization mechanism:

```python
# Task A: cookie extraction
terminal("ssh mac 'sqlite3 ...' > /tmp/raw.txt && python3 decrypt.py", background=True, notify_on_complete=True)

# Task B: browser health check  
terminal("curl http://localhost:9377/health && curl -X POST http://localhost:9377/tabs ...", background=True, notify_on_complete=True)

# When both notify completion: combine results
```

Each background task gets its own terminal session. Use `process(action="poll")` to check status, `process(action="log")` for output. This is NOT true subagent parallelization (no LLM reasoning per task) but works for deterministic shell workflows that don't need reasoning.
