---
name: hermes-payload-composition
description: >
  Understand what Hermes sends to the model on each API call — system prompt layers,
  tool schemas, message history, and memory injection. Includes tool_search progressive
  disclosure analysis (v0.15.1+). Use when optimizing token costs, debugging context
  bloat, explaining what the model sees, or deciding whether to enable tool_search.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [hermes, payload, tokens, context, tool-search, cost]
    related_skills: [hermes-context-management, hermes-agent]
---

# Hermes Payload Composition

## When to Use

- User asks "what does the model see" or "analyze the payload"
- Debugging context bloat or unexpected token costs
- Deciding whether to enable/disable tool_search
- Explaining tool_search to the user
- Optimizing cost per API call

## Payload Breakdown (Typical Setup)

Measured on a Hermes instance with 2 MCP servers, ~230 skills, mimo-v2.5-pro orchestrator.

```
┌─────────────────────────┬──────────┬──────────────────────────────┐
│ COMPONENT               │ TOKENS   │ DETAIL                       │
├─────────────────────────┼──────────┼──────────────────────────────┤
│ 1. SYSTEM PROMPT        │ ~5,500   │                              │
│  ├─ Identity (stable)   │  ~1,100  │ core_guidance constants      │
│  ├─ Custom persona      │  ~900    │ identity + style rules       │
│  ├─ Memory + user       │  ~860    │ Hindsight + user profile     │
│  ├─ Skills index        │ ~2,000   │ names + descriptions (~230)  │
│  ├─ Tool enforcement    │  ~375    │ provider-specific guidance   │
│  └─ Env/profile/meta    │  ~250    │ hints, profile, timestamp    │
│                         │          │                              │
│ 2. TOOL SCHEMAS (JSON)  │ ~6,200   │ BIGGEST VARIABLE             │
│  ├─ Core (25 tools)     │ ~2,500   │ terminal, file, browser...   │
│  ├─ MCP servers (23)    │ ~2,100   │ scrapling, meta-ads          │
│  ├─ Plugins (8)         │  ~600    │ skills, memory, hindsight    │
│  └─ Other (5)           │ ~1,000   │ delegation, cron, image      │
│                         │          │                              │
│ 3. MESSAGES             │ ~3,100   │                              │
│  ├─ History (10 turns)  │ ~2,000   │ conversation context         │
│  ├─ User message        │  ~125    │ current request              │
│  ├─ Tool results        │  ~750    │ execution returns            │
│  └─ Memory injection    │  ~250    │ relevant memories            │
├─────────────────────────┼──────────┼──────────────────────────────┤
│ TOTAL                   │~14,800   │ per API call                 │
└─────────────────────────┴──────────┴──────────────────────────────┘
```

**Key insight**: Tool schemas are 42% of total payload. System prompt is 37%. Messages are 21%.

## System Prompt Layers

Built in `agent/system_prompt.py`, function `build_system_prompt_parts()`.

Three tiers ordered for cache optimization:
1. **Stable** (cached, never changes mid-session): identity, tool enforcement, skills index, environment hints
2. **Context** (project-level files): repo-local instruction files injected from cwd
3. **Volatile** (changes per turn): memory files, user profile, session metadata

The whole string is one cached block for prompt cache hits across turns.

## Tool Search: Progressive Disclosure (v0.15.1+)

Introduced in commit `369075dc9`, shipped with v0.15.1 (v2026.5.29).

### Mechanism

Non-core tools are replaced by 3 bridge tools:
- `tool_search` — search the tool catalog by keyword
- `tool_describe` — get full schema for a specific tool
- `tool_call` — execute via normal dispatch (guardrails, hooks, approval all fire)

Core tools (`toolsets._HERMES_CORE_TOOLS`, ~25 tools) are NEVER deferred.

### Activation

```yaml
tools:
  tool_search:
    enabled: on    # auto (default) | on | off
    threshold_pct: 10
    search_default_limit: 5
    max_search_limit: 20
```

- `auto`: activates when deferrable tokens exceed `threshold_pct` (default 10%) of model context
- `on`: always active when at least 1 deferrable tool exists. **Recommended.**
- `off`: always send all tools

### CRITICAL PITFALL: `auto` Mode Almost Never Activates

The default `auto` with `threshold_pct: 10` requires deferrable schemas to exceed 10% of the model's context window. With typical setups:

- 2 MCP servers + 23 plugin tools = ~7,165 deferrable tokens
- mimo 128K context × 10% = 13,107 threshold → **never activates**
- Even 10 MCP servers (~8,000 tokens) won't trigger auto on 128K+ models

**Always set `enabled: on` in config.**

### Measured Token Savings (W.Alter setup)

48 core + 23 plugin + ~23 MCP tools at runtime:

| Metric | Without TS | With TS | Savings |
|--------|-----------|---------|---------|
| Tools per API call | ~94 | 51 (48 core + 3 bridge) | 43 fewer |
| Tool schema tokens | ~26,700 | ~19,923 | ~6,800 (25%) |
| Total payload tokens | ~35,300 | ~28,500 | ~6,800 (19%) |

**No quality loss.** Verified with 39/39 unit tests. Core tools (terminal, file, browser, web_search, etc.) always visible.

### Tools vs Skills — Common Confusion

Users often think tools already work like skills (on-demand). Before v0.15.1 they didn't:

| | Skills | Tools |
|---|---|---|
| What | Knowledge documents | Callable functions with JSON schemas |
| Injection | Index in system prompt (~2K tok for 230 skills) | Full JSON schema in `tools` API param (~6K tok) |
| On-demand | `skill_view()` loads full content | `tool_search` then `tool_describe` then `tool_call` |
| Pre-v0.15.1 | Already on-demand | ALL sent every call |
| Post-v0.15.1 | Still on-demand | Also on-demand (if over threshold) |

### Implementation Files

- `tools/tool_search.py` — bridge tools, catalog assembly, dispatch
- `agent/tool_executor.py` — `_tool_search_scoped_names()` scopes to session toolsets
- `model_tools.py` — integrates with tool discovery

## Pitfalls

- Tool search config change requires `/reset` (like all tool changes).
- The catalog is stateless (rebuilt every assembly) — prevents silent tool dropouts.
- CLI shows underlying tool name, not bridge name — transparent to user.
- "Non-core" includes MCP, plugin, AND custom tools. Not just MCP.
- Each MCP server contributes 10-20 tool schemas. Adding a new MCP server increases payload significantly.
- The `CHARS_PER_TOKEN` constant (4.0) slightly underestimates — errs toward activating tool_search rather than not.
- Bridge tools add ~378 tokens overhead — only worth it when deferrable tools exceed ~1,000 tokens.
- BM25 keyword matching — model must search with relevant terms to find tools.
- Scope gating: restricted subagents can only call tools in their scope, even via tool_call.

## Verification

```bash
# Run tool_search tests
cd ~/.hermes/hermes-agent && source venv/bin/activate && python -m pytest tests/tools/test_tool_search.py -q

# Count tools (boot-time, excludes MCP runtime tools)
cd ~/.hermes/hermes-agent && python3 -c "
import sys, os; os.environ['HERMES_HOME'] = os.path.expanduser('~/.hermes'); sys.path.insert(0, '.')
from tools.registry import registry; from model_tools import discover_builtin_tools
discover_builtin_tools()
names = registry.get_all_tool_names()
from toolsets import _HERMES_CORE_TOOLS; core = set(_HERMES_CORE_TOOLS)
non_core = [n for n in names if n not in core]
print(f'Total: {len(names)} | Core: {len(core)} | Deferrable: {len(non_core)}')
"
```

## Implementation Files

```python
import sys, json; sys.path.insert(0, '.')
from tools.registry import registry
from model_tools import discover_builtin_tools
discover_builtin_tools()
all_names = registry.get_all_tool_names()
total = sum(len(json.dumps(registry.get_schema(n))) for n in all_names)
print(f"{len(all_names)} tools, {total:,} chars, ~{total//4:,} tokens")
```

For system prompt: read `agent/system_prompt.py`, function `build_system_prompt_parts()`.
For messages: query the session database for message composition by role.
