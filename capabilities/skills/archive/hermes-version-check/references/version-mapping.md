# Hermes Version Mapping

Git tags use date format. Human-readable release names come from commit messages.

| Git Tag | Release Name | Date |
|---------|-------------|------|
| v2026.5.29.2 | v0.15.2 | 2026-05-29 |
| v2026.5.29 | v0.15.1 | 2026-05-29 |
| v2026.5.28 | v0.15.0 | 2026-05-28 |
| v2026.5.16 | v0.14.0 | 2026-05-16 |
| v2026.5.7 | v0.13.x | 2026-05-07 |

## How to Resolve

```bash
# Find human-readable name for current tag
cd ~/.hermes/hermes-agent
TAG=$(git describe --tags --abbrev=0)
git log --oneline --all | grep -iE "bump version|release v" | head -3
# Example: "e71a2bd11 chore: release v0.15.1 (2026.5.29)" → v2026.5.29 = v0.15.1
```

## Key Features by Release

### v0.15.x (v2026.5.28-29)
- **tool_search**: Progressive tool disclosure — MCP/plugin tools replaced by bridge tools (tool_search, tool_describe, tool_call). ⚠️ Default `auto` mode almost NEVER activates (requires deferrable tools > 10% of context = ~13K tokens on 128K model). Set `enabled: on` in config. See `hermes-tool-search-config` skill.
- SQLite FTS5 graceful degradation
- Explainer for abnormal turn endings
- `/compress here [N]` boundary-aware compression

### v0.14.0 (v2026.5.16)
- `/handoff` live session transfer
- `hermes proxy` OpenAI-compatible local proxy
- `x_search` native X search via Grok
- `computer_use` for any vision model
- CDP browser 180x faster (WebSocket persistent)
- Cold start -19s
- Claude cross-session 1h cache
- LINE + SimpleX Chat (22 platforms)
- Microsoft Teams end-to-end
