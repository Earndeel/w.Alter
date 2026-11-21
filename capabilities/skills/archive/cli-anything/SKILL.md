---
name: cli-anything
category: software-development
description: "CLI-Anything integration — 76+ agent-native CLIs for software that wasn't built for agents. Install, discover, and use CLIs for Blender, Exa, DrawIO, ComfyUI, n8n, Obsidian, and more."
tags: [cli-anything, cli-hub, agent-native, tools, software]
---

# CLI-Anything — Agent-Native Software CLIs

## When to Use

- Need to control software that has no native CLI/API/MCP (Blender, GIMP, DrawIO, etc.)
- Fallback when no existing tool, skill, or MCP server covers the capability
- Searching for available agent-native CLIs via `cli-hub search`
- On-demand installation of a single CLI for a specific task

**Priority rule:** Always check for existing CLI/API/MCP first. CLI-Anything is the last resort.

## What It Is
CLI-Anything (by HKUDS/HKU) wraps existing software into agent-friendly CLIs with `--json` output. Each CLI has a SKILL.md that teaches agents how to use it.

**Hub**: `cli-hub` CLI manages installation and discovery.
**Source**: https://github.com/HKUDS/CLI-Anything

## Quick Reference

### Discovery
```bash
cli-hub list                          # All available CLIs
cli-hub search <keyword>              # Search by name/description/category
cli-hub info <name>                   # Details on a specific CLI
```

### Installation
```bash
cli-hub install <name>                # Install a CLI
cli-hub uninstall <name>              # Remove it
cli-hub update <name>                 # Update to latest
```

### Usage
```bash
cli-hub launch <name> -- <args>       # Run an installed CLI
# Or directly: cli-anything-<name> <args>
# ALL CLIs support --json for machine-readable output
```

## Usage Philosophy
**This is a passive tool in the arsenal.** Do NOT proactively install CLIs or suggest batch installations. When a specific task needs a capability that CLI-Anything covers, install just that one CLI on-demand, use it, done.

**Priority rule (Lucas):** Always look for an existing CLI/API/MCP first. Use CLI-Anything ONLY as a fallback when nothing native exists. Sequence: (1) existing tool/skill/MCP → (2) `cli-hub search` → (3) install on-demand.

## Integration Pattern
```bash
# 1. Discover if a CLI exists for the task
cli-hub search <capability>

# 2. Install on-demand (only when actually needed)
cli-hub install <name>

# 3. Use with --json for structured output
cli-anything-<name> <command> --json
```

Some CLIs (zotero, browser) also expose MCP servers — configurable in `config.yaml` under `mcp_servers`.

## Key Convention
ALL CLI-Anything CLIs support `--json` at the root level for machine-readable output. ALWAYS use `--json` when calling from Hermes.

## Available Categories (76+ CLIs)
3D, AI, audio, automation, communication, data-science, database, debugging, design, devops, diagrams, finance, game, gamedev, generation, graphics, image, knowledge, mobile, music, network, office, osint, project-management, science, scientific, search, streaming, testing, video, web. Browse with `cli-hub list`.

## Pitfalls
- **PEP 668 / externally-managed environments**: `cli-hub install` may fail with `--break-system-packages` error. Fix: `export PIP_BREAK_SYSTEM_PACKAGES=1` before installing, or use pipx.
## Lucas's Operating Directive
**Priority order for any capability:**
1. Existing CLI/API/MCP → use directly
2. Nothing available → CLI-Anything as fallback only

Do NOT proactively suggest or install CLI-Anything CLIs when a native tool, existing skill, or direct API call can do the job. CLI-Anything is a last resort, not the default.

Do NOT explain that CLI-Anything needs "API keys" generically — each CLI wraps different software. Some need nothing (drawio, mermaid), some need SaaS credentials (exa, zoom). Explain per-CLI, not blanket.

## Pitfalls
- Some CLIs require backend software installed (Blender, GIMP, etc.) — check `cli-hub info <name>` for prerequisites
- Some CLIs are npm-based (elevenlabs, sentry, feishu) — need Node.js
- Some require API keys (exa, anygen, zoom) — check per-CLI before installing
- The hub is growing fast — re-check `cli-hub list` periodically for new additions
- `pip install` may need `PIP_BREAK_SYSTEM_PACKAGES=1` env var on system Python (Debian/Ubuntu PEP 668)
- `hacker-feeds-cli` has a broken module import (as of v0.3.0) — skip it until fixed
