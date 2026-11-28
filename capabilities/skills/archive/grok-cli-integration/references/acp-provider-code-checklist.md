# ACP Provider Code Integration Checklist

Concrete integration points when adding a new CLI/ACP subprocess-backed
provider to the Hermes CLI codebase. Follow this order; each step depends on
the previous.

## 1. Generalize the ACP transport (if first new provider)

File: `agent/copilot_acp_client.py`

Convert single-provider hardcoded functions to a dispatch table:

```python
_ACP_PROVIDER_DEFAULTS: dict[str, dict] = {
    "copilot-acp": {
        "command_fallback": "copilot",
        "args_fallback": ["--acp", "--stdio"],
        "marker_base_url": "acp://copilot",
        "env_overrides": {"COPILOT_ACCESS_TOKEN": None, "GITHUB_TOKEN": None},
        "command_env": "HERMES_COPILOT_ACP_COMMAND",
    },
    "grok-cli": {
        "command_fallback": "grok",
        "args_fallback": ["agent", "-m", "grok-4.5", "stdio"],
        "marker_base_url": "acp://grok-cli",
        "env_overrides": {"XAI_API_KEY": None, "XAI_BASE_URL": None},
        "command_env": "HERMES_GROK_CLI_PATH",
    },
}
```

Each provider entry needs:
- `command_fallback`: CLI binary name
- `args_fallback`: default subprocess args (including model if fixed)
- `marker_base_url`: `acp://<provider-id>` — used for routing
- `env_overrides`: env vars to unset for this provider (prevents API-key
  path from interfering with CLI OAuth path)
- `command_env`: env var for user override of the binary path

Make `_resolve_command(provider_id)`, `_resolve_args(provider_id)`,
`_build_subprocess_env(provider_id)` all accept `provider_id` and route
through the dispatch table.

Update `CopilotACPClient.__init__` to accept `provider_id` and pass it
through to the resolver functions.

## 2. Provider overlay and aliases

File: `hermes_cli/providers.py`

Three changes:
1. Add `HermesOverlay` entry in `HERMES_OVERLAYS`:
   ```python
   "grok-cli": HermesOverlay(
       transport="codex_responses",
       auth_type="external_process",
       base_url_override="acp://grok-cli",
       base_url_env_var="GROK_CLI_BASE_URL",
   ),
   ```
2. Add aliases in the `ALIASES` dict: `"grok": "grok-cli"`
3. Add display label in `_LABEL_OVERRIDES`: `"grok-cli": "Grok CLI (ACP)"`

## 3. Auth registry

File: `hermes_cli/auth.py`

Three functions to generalize (not duplicate):

`get_external_process_provider_status(provider_id)`:
- Look up `_ACP_PROVIDER_DEFAULTS[provider_id]` from `agent.copilot_acp_client`
- Check command env var (`HERMES_GROK_CLI_PATH`, etc.) for user overrides
- Check binary existence with `shutil.which`
- Built-in: `command in ("grok", "") or command.endswith("grok")`
- Apply `env_overrides` via `env -u KEY` prefix
- Default status: `configured=True`, `logged_in=True` (external process)

`resolve_external_process_provider_credentials(provider_id)`:
- Set `api_key=provider_id`, `base_url=acp://<provider-id>`
- Set `command`, `args`, `source="process"`

`get_auth_status(target)`:
- Add dispatch: `if target == "grok-cli": return get_external_process_provider_status(target)`

## 4. Runtime agent helpers

File: `agent/agent_runtime_helpers.py`

In `_resolve_provider_client()`, add grok-cli handling alongside copilot-acp:
```python
if (agent.provider in ("copilot-acp", "grok-cli")
        or str(client_kwargs.get("base_url", "")).startswith("acp://")):
    from agent.copilot_acp_client import CopilotACPClient
    client = CopilotACPClient(provider_id=agent.provider, ...)
```

## 5. Agent init

File: `agent/agent_init.py`

Two changes:
1. API mode guard: skip API key requirement for external_process providers:
   ```python
   and agent.provider != "grok-cli"
   and not str(agent.base_url or "").lower().startswith("acp://grok-cli")
   ```
2. Client kwargs for ACP command/args:
   ```python
   if agent.provider == "grok-cli":
       client_kwargs["command"] = agent.acp_command
       client_kwargs["args"] = agent.acp_args
   ```

## 6. Auxiliary client

File: `agent/auxiliary_client.py`

Two changes:
1. Add aliases in `_AUXILIARY_PROVIDER_ALIASES`:
   ```python
   "grok": "grok-cli",
   "xai-cli": "grok-cli",
   ```
2. In `resolve_provider_client()`, add grok-cli handling inside the
   `external_process` auth_type branch (after copilot-acp block):
   ```python
   if provider == "grok-cli":
       api_key = str(creds.get("api_key", "")).strip()
       base_url = str(creds.get("base_url", "")).strip()
       command = str(creds.get("command", "")).strip()
       from agent.copilot_acp_client import CopilotACPClient
       client = CopilotACPClient(
           provider_id="grok-cli",
           api_key=api_key,
           base_url=base_url,
           command=command,
       )
       return client, final_model
   ```

## 7. Plugin files

Create `plugins/model-providers/grok-cli/plugin.yaml`:
```yaml
name: grok-cli-provider
kind: model-provider
version: 1.0.0
description: xAI Grok CLI via ACP subprocess
author: Nous Research
```

Create `plugins/model-providers/grok-cli/__init__.py` with a
`GrokCLIProviderPlugin` class exposing:
- `get_provider_name()` → `"grok-cli"`
- `get_models()` → list of model dicts with `id` and `provider`
- `get_default_env_overrides()` → `XAI_API_KEY`, `XAI_BASE_URL`

## Pitfalls

### `replace_all=true` creates dead code
When using `patch` with `replace_all=true`, if the same code block appears
in both the old provider's section AND the new one you just added (e.g.
the catch-all fallback), it duplicates in both places. The second instance
becomes unreachable dead code. **Never use `replace_all` on provider
dispatch blocks.** Always use targeted single-replacement with unique
surrounding context lines.

### Test imports must match actual codebase exports
The providers module uses `ALIASES` (not `PROVIDER_ALIASES`) and
`_LABEL_OVERRIDES` (not `get_provider_label`). Always verify with
`search_files` before writing test assertions against these names.

### Agent import path for tests
The `CopilotACPClient` is at `agent.copilot_acp_client`, not
`hermes_cli.acp_client`. The `agent/` package is at the repo root, same
level as `hermes_cli/`.

### Plugin import path for tests
Plugin tests need `sys.path` manipulation to import from
`plugins/model-providers/grok-cli/`. Pop the path in a `finally` block
to avoid test pollution.

## Verification

```bash
# Run all grok-cli provider tests
python3 -m pytest tests/test_grok_cli_provider.py -v

# Run a specific test
python3 -m pytest tests/test_grok_cli_provider.py::test_grok_cli_overlay_registered -v

# Smoke test the actual CLI (requires auth)
grok --no-auto-update -p "Say exactly: ok."
```
