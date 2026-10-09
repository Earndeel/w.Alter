---
name: hermes-tool-search-config
description: >
  Configure Hermes tool_search for optimal token savings. Progressive tool
  disclosure — replaces MCP and plugin tool schemas with 3 bridge tools.
  Critical pitfall: "auto" mode almost never activates for typical setups.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [hermes, tools, mcp, tokens, optimization, tool_search]
---

# Hermes Tool Search Configuration

Progressive tool disclosure introduced in v0.15.1 (v2026.5.29). Replaces MCP and plugin tool schemas with 3 bridge tools (`tool_search`, `tool_describe`, `tool_call`). Core tools are NEVER deferred.

## When to Use

- Configuring or troubleshooting tool_search behavior
- Optimizing token usage when MCP servers or plugins are installed
- User asks about reducing tool schema token cost

## Activation Modes

| Mode | Behavior |
|------|----------|
| `off` | Disabled. All tools always visible. |
| `auto` | Activates when deferrable tokens exceed 10% of model context. |
| `on` | Always activates when at least 1 deferrable tool exists. **Recommended.** |

## CRITICAL PITFALL: `auto` Mode Almost Never Activates

The default `auto` with `threshold_pct: 10` requires deferrable schemas to exceed 10% of the model's context window. With typical setups:

- 2 MCP servers + 23 plugin tools = ~7,165 deferrable tokens
- mimo 128K context × 10% = 13,107 threshold → **never activates**
- Even 10 MCP servers (~8,000 tokens) won't trigger auto on 128K+ models

**Always set `enabled: on` in config.**

## Config

Set in `hermes config edit` or `hermes config set`:

```yaml
tools:
  tool_search:
    enabled: on
    threshold_pct: 10
    search_default_limit: 5
    max_search_limit: 20
```

## Token Impact (measured on W.Alter setup)

48 core + 23 plugin + ~23 MCP tools at runtime:

| Metric | Without TS | With TS | Savings |
|--------|-----------|---------|---------|
| Tools per API call | ~94 | 51 (48 core + 3 bridge) | 43 fewer |
| Tool schema tokens | ~26,700 | ~19,923 | ~6,800 (25%) |
| Total payload tokens | ~35,300 | ~28,500 | ~6,800 (19%) |

## Quality Impact

**No quality loss.** Verified with 39/39 unit tests. Core tools (terminal, file, browser, web_search, etc.) always visible. Deferrable tools are rarely-used plugins discovered via BM25 search on demand.

## Verification

```bash
# Run tests
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

## Implementation

- `tools/tool_search.py` — main module (assemble_tool_defs at line 529, should_activate at line 234)
- `toolsets._HERMES_CORE_TOOLS` — core tools that are never deferred
- `hermes_cli/config.py` line 1813 — config defaults
- `agent/tool_executor.py` line 148 — unwrap logic for tool_call bridge

## Pitfalls

- After changing `enabled`, need `/reset` — tools array is cached per session
- MCP tools only appear after gateway connects — not in boot-time discovery
- Bridge tools add ~378 tokens overhead — only worth it when deferrable tools exceed ~1,000 tokens
- BM25 keyword matching — model must search with relevant terms to find tools
- Scope gating: restricted subagents can only call tools in their scope, even via tool_call
