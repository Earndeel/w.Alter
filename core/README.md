# Walter shared capabilities

Walter owns reusable capabilities and their data; Hermes, DSH, Codex and Claude Code own their execution loops and permission gates. Optional modules load only when called, so one missing module does not prevent memory or skills from starting.

`modules/registry.json` declares 16 logical modules: source boundaries, interfaces, owned data, dependencies, backup paths, per-harness bindings and explicit limits. `walter_platform` validates this registry without importing a harness. The encrypted backup reads the same declared paths and fails if required anchors disappear.

## Commands

- `walter modules`: contracts and interfaces, not a health certification.
- `walter check`: required files and static forbidden imports in declared shared cores.
- `walter status`: installation plus observed systemd service states (no paid requests, desktop control or secret retrieval).
- `walter harness check codex|claude-code|dsh|hermes`: actual configuration, kept native features and independent bindings. Configuration is distinct from already loaded processes.
- `walter harness attach codex|claude-code|dsh [--home PATH]`: preview common MCP attachment. `--apply` backs up and writes atomically; identical state is a no-op, conflicting custom Walter configuration is refused. This installs the MCP connection only, not a new runtime, tokens, model provider or context engine. Existing full compositions remain separately managed and verified.
- `walter backup-paths`: declared module paths for offsite coverage.

## Common MCP surface

The existing memory, skills, raw vault, logs, profile and browser-session tools remain. New thin ports in `walter_capabilities.py` add `walter_modules`, `walter_browse`, `secret_search`, `secret_reference`, `model_route`, and `computer_use`. All optional-module errors stay local and omit sensitive exception text. Fresh MCP connections discover the tools; already running clients need reconnection.

Computer Use is local stdio only. Scope ceilings are provisioned in `modules/computer-policy.json`; a tool argument cannot grant authorization. The host MCP approval gate and user's task govern actions, including screen pixels. Unknown client tags receive no scopes. This is not a bypass of a host permission system. Standalone vision is unavailable until a sensor is configured. Hermes keeps its own central approval and human-presence handling through its native adapter.

Secrets returns metadata/references only. Use the local `walter-secret exec` under the calling harness's execution permissions to inject values. The child output is suppressed, including transformed values; there is no generic shell executor or raw password tool in MCP.

Browse uses the same request validation, routing and storage as Hermes. Session names cannot escape the module's state root. Browser authentication is a separate explicit integration in `browser_auth.py`.

## Proof and scope

Unit tests cover independent optional modules, secret nondisclosure, per-call authorization, config preservation/idempotence/races, and source boundaries. Protocol tests perform a fresh MCP handshake, list tools and invoke safe read-only operations. Computer Use validation uses synthetic devices, not Monsieur's desktop. A directory, manifest or passing import test alone does not establish a complete live user journey.

Data currently under `.hermes` can remain at a compatibility path without requiring a running Hermes process. Source migration and adapters are recorded individually; no claim of complete clean-VM restoration is made by the registry.
