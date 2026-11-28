# Runtime reload boundaries

Use this when source/config changes pass tests but Hermes Desktop still shows stale providers, models, themes, or labels.

## Ownership map

| Layer | Typical owner | What its restart reloads | What it does not reload |
|---|---|---|---|
| Electron app | macOS `Hermes.app` process | renderer bundle, launchctl environment, local Electron state | remote dashboard Python modules |
| Dashboard | `hermes-dashboard.service` / `hermes_cli.main dashboard` | server modules, provider registry, shared API state | unrelated standalone TUI sessions |
| TUI session | terminal/tmux `hermes --tui` tree | that session's Node UI and gateway | dashboard service and other TUI sessions |
| Session worker | `tui_gateway.slash_worker` | one conversation/model worker | parent registry and renderer |

## Diagnosis

1. Record PID, PPID, start time, command, cwd, ports, and service/cgroup for every candidate.
2. Use the parent tree to distinguish shared service children from standalone tmux/TUI trees.
3. Compare process start time with the patch time.
4. Inspect the service cgroup before restarting; shared dashboards may own active workers, MCP servers, LSPs, proxies, and user jobs.
5. State the evidence precisely: "source patched and fresh-process tests pass" is not "the running UI is fixed."

## Safe verification ladder

1. Verify source syntax/tests.
2. Exercise the changed function in a fresh process.
3. Reload only the owning runtime when its blast radius is acceptable.
4. Query the live API used by the renderer, if available.
5. Open the actual picker and confirm both inclusion and exclusion requirements.

## Guardrails

- Do not restart Electron as a proxy for reloading a remote backend.
- Do not label duplicate or old processes as orphaned from age alone.
- Do not kill broad process-name matches (`pkill`, `killall`).
- If the required owner is a shared dashboard, request a maintenance window or explicit approval after reporting affected children.
- Never claim visual success without observing the live rendered result after the correct reload.
