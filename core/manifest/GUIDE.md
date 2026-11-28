# walter-core — detailed guide

## Purpose
The common harness of W.Alter: it presents the modules to agents, exposes their capabilities under the same names in
every runtime (Walter Engine, Claude Code, Codex) and installs the connections. It replaces neither the runtime nor
its permissions. It also hosts the core components: the engine, identity (Soul), security (policy, secrets),
interfaces (web Portal, Telegram, API).

## Documentation of W.Alter (D1 / D2 / D3)
Every entity has three depths, read with `module_guide(path, depth)`:

| Depth | Content | Source |
|---|---|---|
| D1 | What it is (a definition) and how to open D2 | W.Alter: `/walter/docs/manifest/SUMMARY.md`; module: `manifest/SUMMARY.md`; component: its `role` in the module contract |
| D2 | Role and scope, organisation, tools and interfaces, where to check the live state, and its children (generated from the registry) | W.Alter: `/walter/docs/manifest/MANIFEST.md` + the modules; module: `manifest/MANIFEST.md` (+ a live part the module generates) + its components; component: its contract entry and README header |
| D3 | Technical detail: components, interfaces per runtime, data, privacy, limits, source paths | W.Alter: `/walter/docs/manifest/GUIDE.md`; module: `manifest/GUIDE.md` (or its README); component: its README |

Paths: `walter`, a module id, or `module/component`. Any depth can be read directly. `module_index(module, section)`
gives a module's live contents (skills per domain, router tasks). A module that shares another's folder keeps its
presentation below it (`/walter/cognition/memory/manifest/logs/`). Nothing is copied elsewhere: the registry
(`/walter/core/modules/registry.json`, compiled from the contracts by `walter contracts render`) points to these files.

## Organisation
| Part | Role |
|---|---|
| `server.py`, `walter_capabilities.py` | MCP server `walter`: thin ports to the modules; toolsets per client (`config/toolsets.toml`) |
| `walter_platform/` | Contracts, registry, paths, instance, presentation, release, harness connections |
| `hooks/walter_hook.py` | Runtime adapter for external agents: memory context per message, session logging, bus events |
| `engine/` | Walter Engine, the single production runtime (sessions, agent loop, tools, sub-agents, Engine API) |
| `identity/` | walter-soul: renders the Soul for each runtime |
| `security/` | Execution policy (`walter_security`), Walter Secrets |
| `interfaces/` | Doors to the engine: web Portal, Telegram |
| `modules/catalog.json` → `registry.json` | Contract catalogue and compiled registry |

## Interfaces
CLI `walter`: `modules`, `status`, `check`, `doctor`, `path`, `instance`, `layout`, `present notes|note|catalog|manifest|index|doc`.

## Limits
- MCP server instructions are fixed when the server starts: a module added or changed appears in the next session.
- An unavailable module disables its own tools, not the others.
