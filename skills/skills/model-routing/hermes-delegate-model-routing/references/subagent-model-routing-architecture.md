---
name: subagent-model-routing-architecture
description: "How subagent model routing actually works in Hermes Agent (code-verified architecture). Use when an orchestrator agent calling delegate_task needs to know what it can and cannot control about the subagent's model."
tags: [hermes, delegate_task, subagent, model-routing, architecture]
---

# Subagent Model Routing — Architecture

What an orchestrator agent calling `delegate_task` actually controls about subagent model selection. Code-verified against the installed `~/.hermes/hermes-agent/tools/delegate_tool.py` (3105 lines) and `tools/async_delegation.py` (386 lines), read directly.

## The Two-Surface Rule

Subagent model routing in Hermes has **two surfaces** that are easy to conflate:

1. **YAML file surface** (the only one that works). All subagents of a session profile share the routing block. Read at gateway startup.
2. **Tool-call surface** (does not work for model). The LLM caller picks goals, contexts, toolsets, role, background — but **not** the model.

The orchestrator cannot say "this subagent on Claude, that one on MiMo" within a single session profile. The model is a session-profile-level decision, not a per-call decision.

## What the Tool Schema Exposes

`DELEGATE_TASK_SCHEMA["parameters"]["properties"]` (line ~2945 of `delegate_tool.py`) — these are the only fields the LLM caller can set:

| Field | Purpose |
|---|---|
| `goal` | What the subagent should accomplish |
| `context` | Background info (subagent has no parent history) |
| `toolsets` | Toolsets to enable (intersected with parent's enabled toolsets) |
| `tasks` | Batch of sub-tasks (up to 3 concurrent by default) |
| `tasks[].role` | `leaf` (default) or `orchestrator` (can re-delegate) |
| `tasks[].acp_command` / `tasks[].acp_args` | Per-task ACP transport override |
| `role` | Top-level role, default `leaf` |
| `background` | `true` = async delegation, returns immediately with `delegation_id` |
| `acp_command` / `acp_args` | Top-level ACP transport override |

**Not in the schema**: `model`, `provider`, `api_key`, `base_url`, `api_mode`. The handler does not accept them. The `delegate_task()` function signature (line ~2044) does not declare them.

Verify on a running install:
```python
import inspect
from tools.delegate_tool import DELEGATE_TASK_SCHEMA
print(list(DELEGATE_TASK_SCHEMA["parameters"]["properties"].keys()))
# Expected: ['goal', 'context', 'toolsets', 'tasks', 'role', 'background', 'acp_command', 'acp_args']
```

## How the Model Actually Gets Resolved

The model is read by `_resolve_delegation_credentials()` (line ~2621) from the routing block in the YAML file, then passed to `_build_child_agent()` (line ~963) which constructs the child `AIAgent`. Three modes:

1. **`base_url` set** → use that direct OpenAI-compatible endpoint. Provider forced to `custom`. `api_mode` auto-detected from URL (e.g. `api.anthropic.com` → `anthropic_messages`).
2. **`provider` set** (no `base_url`) → resolve full credential bundle via `hermes_cli.runtime_provider.resolve_runtime_provider(requested=provider)`. Provider name must match a `providers:` entry in the YAML file.
3. **Neither set** → child inherits parent's model and credentials. **Silent fallback** — no warning.

If the API key in the routing block is empty but the parent has the key in env (e.g. `MINIMAX_API_KEY`, `DASHSCOPE_API_KEY`), the child inherits it via `effective_api_key = override_api_key or parent_api_key`. This is the documented design for non-`OPENAI_API_KEY` providers.

## Async Delegation (`background=true`)

`tools/async_delegation.py::dispatch_async_delegation()` accepts a `model` parameter (line ~152) — but **for audit only**. The value:
- Gets captured at dispatch time into the registry record
- Gets carried in the completion-event payload
- Comes from the resolved YAML, not from the LLM's call

The async path delegates the actual child build back to `delegate_tool._run_single_child` via an injected `runner` callable. Async tasks use the same routing model as sync tasks.

## Workarounds for Per-Task Model Differences

When the orchestrator genuinely needs different models for different sub-tasks:

1. **Multiple profiles**: create `~/.hermes/profiles/worker-cheap/config.yaml` with its own `model:` and routing blocks, then route via `delegate_task(tasks=[...], acp_command="copilot", ...)` from a different parent profile. The child profile's `model.default` is what runs.
2. **ACP transport**: `tasks[].acp_command` lets a single parent spawn children with different ACP-compatible CLIs. Each child profile carries its own model config.
3. **Manual direct API calls**: when a subagent model is misbehaving, call the target API directly via `urllib.request` or `terminal` with `curl` — bypass the subagent system entirely. Use this for one-off fetches, not for multi-turn agentic work.

## What Doesn't Work (Common Misconceptions)

- ❌ **Per-task `model` field in `tasks[]`**: not in the current schema. Some earlier documentation suggested it, but the current code does not expose it.
- ❌ **Passing `model=` kwarg to `delegate_task(...)` from a Python script**: the function signature does not declare it; the value is silently dropped.
- ❌ **Editing the YAML and expecting immediate effect**: `CLI_CONFIG` is loaded at gateway startup. Restart required.
- ❌ **Assuming the child uses the parent's provider because the parent's API key is set**: the child's `effective_provider` comes from the routing YAML, which may be a different provider than the parent. The child uses its own provider's credentials, with `api_key` inheriting from parent only when empty.

## Verification Chain

To confirm a subagent runs on the expected model:

1. **Check the result JSON returned to the parent.** Each task entry includes a `model` field.
2. **Cross-check against the routing block in the YAML file.** Mismatch = either gateway not restarted, or `_resolve_delegation_credentials` is returning a different value than expected.
3. **Trace `_resolve_delegation_credentials` directly:**
   ```python
   import inspect
   from tools.delegate_tool import _resolve_delegation_credentials
   print(inspect.getsource(_resolve_delegation_credentials))
   ```
4. **Check the child's `AIAgent.model` attribute** if you have access to the child object (internal testing only).

## Quick Diagnostic

If a subagent runs on the wrong model:

1. Read the value of the routing block's `model` key and confirm it matches the expected model name.
2. Restart the gateway (`pkill -f hermes-gateway` then restart via systemd or your launcher).
3. Run a trivial `delegate_task` and inspect the result JSON's `model` field.
4. If still wrong, run `_resolve_delegation_credentials` manually with the loaded YAML to see what it returns.

## Related Skills

- `hermes-delegate-task-routing` — recipes for the routing block, gateway restart procedures, and the now-obsolete `_load_config()` patch. The patch's intent (YAML-first merge) is already in the installed code; verify before applying.
- `hermes-multi-agent-profiles` — profile architecture for orchestrator → specialist dispatch. The cleanest way to get per-subagent model routing.
- `hermes-provider-mastery` — provider configuration, credential resolution, and the three-layer config model.
