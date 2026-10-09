---
name: hermes-desktop-operations
description: Use when configuring or troubleshooting Hermes Desktop.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [hermes, desktop, electron, remote, tailscale, themes, plugins]
    related_skills: [hermes-agent]
---

# Hermes Desktop Operations Skill

Class-level workflow for building, configuring, customizing, inspecting, recovering, and troubleshooting Hermes Electron desktop deployments. Keep the renderer, backend, relay, and supervised service as separate layers; use the linked references and scripts for depth without turning each incident into a separate skill.

## When to Use

- Build or adapt Hermes Desktop for a different Mac architecture or a remote/VPS backend.
- Diagnose blank windows, boot loops, host-header failures, token failures, tunnel loss, stale UI, or gateway/setup states.
- Configure SSH/Tailscale connectivity, themes, plugins, renderer state, or live DOM verification.

**Don't use for:** generic Electron application development without Hermes-specific connection, packaging, or renderer-state behavior.

## Prerequisites

- Identify the actual installed bundle, active Hermes home/profile, selected connection, service manager, and process owner before changing anything.
- Read `references/connection-and-recovery.md` for remote connectivity or recovery work.
- Read `references/build-and-ui.md` for builds, themes, plugins, CDP, or live DOM work.
- Keep credentials in the documented config/credential store; redact tokens in output and never commit them.

## Operating Invariants

- Treat the local renderer bundle and the remote backend connection as independent failure domains; a healthy API does not prove that the packaged renderer exists.
- Resolve the active app bundle, profile, saved connection, environment, service owner, and process path before changing state; never infer them from a generic app name or stale source checkout.
- Keep the Dashboard loopback-bound by default. Prefer an SSH loopback tunnel when no server change is desired; for direct Tailscale access, use an explicit Host allowlist, preserve normal token authentication, cover HTTP and WebSocket paths, and supervise the relay.
- Require both remote URL and token for remote mode, keep the real session token aligned across client and service, and treat `/api/status` as a liveness probe only; verify a protected REST route and an authenticated idle WebSocket.
- Back up connection and renderer state before edits, merge appearance records instead of replacing maps, redact tokens, and use graceful app/service restarts with an explicit blast-radius check.
- Verify the live target after reload: process/bundle path, API, WebSocket, renderer DOM, computed styles, and—when appearance matters—the Electron CDP screenshot. Source tests alone are not runtime proof.

## Quick Reference

| Need | First action |
|---|---|
| Blank/white window | Separate renderer asset presence from backend reachability; inspect the installed bundle and both remote variables. |
| `400 Invalid Host` | Use an SSH loopback tunnel, or implement a narrow direct-Tailscale Host policy in the active server version. |
| `401` or setup loop | Compare the saved connection, GUI environment, and live session token; test protected REST and WebSocket routes. |
| `ECONNREFUSED` after sleep | Check the relay/tunnel owner and established connection before restarting the app. |
| Stale labels/providers/themes | Map the owning runtime and restart only that layer after checking blast radius. |
| Theme/UI question | Inspect persisted scope and rendered computed styles; do not validate stored seeds alone. |
| Plugin inventory | Inspect the packaged registry, profile disk plugins, and persisted enablement separately. |

## Procedure

1. **Classify the layer.** Decide whether the failure is in the renderer bundle, Electron environment/config, relay/network, Dashboard/API, gateway, or a stale runtime. Record the exact bundle path, profile, endpoint, process/service owner, and relevant timestamps; completion means every later action has a named target.
2. **Validate the connection contract.** Resolve per-profile saved config, environment overrides, and global remote settings in that order. Remote mode needs both URL and token. GUI launches receive `launchctl` values only after a full quit and relaunch; preserve unrelated connection keys.
3. **Probe progressively.** Check the public status endpoint, a protected REST route, and an authenticated WebSocket held idle beyond the relay's connect timeout. A `200` status response alone is never a healthy-desktop verdict.
4. **Choose the least invasive repair.** Use a loopback SSH tunnel when the server should remain unchanged. For direct Tailscale, keep the Dashboard loopback-bound, allow only explicit Tailscale hosts, retain real token checks, cover the separate WebSocket auth path, and supervise the forwarder.
5. **Reload the owner, not a proxy.** Identify cgroups, parent trees, PIDs, and start times. A Dashboard restart can terminate sessions, MCP servers, LSPs, proxies, and user jobs; do not restart it merely to refresh a label, and never use blanket process-name kills.
6. **Verify the live result.** Re-run the exact probes, confirm the intended bundle/process path, inspect live DOM/computed styles for UI work, and capture the Electron renderer through CDP when visual state matters. Record both required success and required rejection behavior.

## Remote Setup and Recovery

### Saved connections and token scope

The Electron renderer is local; only API/WebSocket traffic uses the remote backend. Connection resolution normally prefers a profile override, then `HERMES_DESKTOP_REMOTE_URL` plus `HERMES_DESKTOP_REMOTE_TOKEN`, then a saved global remote configuration. A URL without a token is an explicit configuration error, not a reason to fall back silently.

The dashboard's status endpoint may be public. A fake token can therefore pass readiness while protected routes return `401`; use the live session token and test the authenticated REST and WebSocket paths. Store the token in the active service and selected client configuration, never in a report or hard-coded launcher output.

### Forwarding choices

An SSH forward terminating on Dashboard loopback is the reversible default when Host validation or server ownership is uncertain. After an upstream socket connects, clear its connect timeout before long-lived bidirectional relay reads; otherwise an idle authenticated WebSocket can reset on a fixed interval.

Direct Tailscale access is a separate authenticated reverse-proxy design. Keep the Dashboard loopback-bound, accept only explicitly configured Tailscale addresses/names in the current Host-validation implementation, preserve protected HTTP authentication, and validate the independent WebSocket upgrade path. Do not bind the Dashboard to `0.0.0.0`, use a public-URL setting as a Host workaround, or replace the token with a sentinel.

### Recovery order

For `ECONNREFUSED`, verify the Mac is online, the Dashboard/gateway services are healthy, the forwarder owns the expected port, and an established connection exists; then repair only the known tunnel/forward. For timeouts, hold the authenticated WebSocket before touching renderer state. For setup/offline labels, query remote status first and distinguish a stopped gateway from a local-mode connection file, missing token, wrong bundle, or stale renderer.

Back up `connection.json` and renderer-state directories before moving them. Keep Cookies, session databases, connection data, and appearance records; use timestamped reversible moves for Local Storage, Session Storage, Cache, GPUCache, and Code Cache only after network probes pass. Never claim recovery from a successful curl alone.

## Build and Adaptation

The desktop backend-resolution ladder may choose a managed install, a verified `hermes` on PATH, system Python, or a bootstrap path before spawning `hermes serve` on loopback. Remote mode uses the supported connection contract and normally needs no source patch. For Intel/custom builds, build on the target architecture with the repository's supported Node/npm and macOS build prerequisites; distinguish the installer bundle from the desktop app and launch the intended binary by absolute path when app registration is ambiguous.

Before claiming a build is usable, verify the packaged renderer entry point, backend readiness, protected API, WebSocket, and the running process's bundle path. A source-level build or fresh-process test does not prove that an already-running Dashboard or Electron app has reloaded it.

## Themes, Renderer State, and CDP

Dashboard themes and Electron desktop themes are independent. Built-in desktop presets require a rebuild; user themes can be merged into the desktop user-theme record in local storage. Use a unique slug, preserve existing records, respect the active/default profile scope, and back up only the appearance keys needed for rollback. Temporary CDP access must bind to loopback, use an isolated profile when probing, and be closed before normal relaunch.

Use native preference keys for features such as the conversation backdrop before adding CSS. Theme seeds are not rendered pixels: inspect computed styles and semantic surfaces for exact-color requirements. Scope persistent CSS narrowly to stable `data-*` attributes, preserve existing typography records, and verify the actual Electron screenshot rather than a generic macOS capture.

For live DOM inspection, use the development CDP port only when it belongs to the intended target. Never relaunch or kill a user's app to obtain the port; use an isolated `HERMES_HOME`, user-data directory, and port for probes. Prefer small projected JSON queries, stable selectors, and computed-style evidence over dumping the whole DOM.

## Plugin Inventory

Report packaged/bundled plugins, active-profile disk/runtime plugins, and effective active plugins as separate buckets. Inspect the real `app.asar` plus `app.asar.unpacked`, the active profile's `desktop-plugins` directory, the packaged registry, and the narrow persisted enable/disable keys. An empty external directory does not prove that the app has no bundled plugins, and an Electron Helper process is not evidence of a Hermes plugin.

## Verification

- [ ] Installed bundle and active profile were identified.
- [ ] Renderer entry point and remote connection were checked independently.
- [ ] Public status, protected REST, and authenticated WebSocket behavior were tested.
- [ ] Host rejection remains enforced for an arbitrary host.
- [ ] Tokens were redacted and connection/appearance changes are reversible.
- [ ] The correct owner was reloaded and its new PID/start time or live renderer was verified.
- [ ] UI changes were checked in the live DOM/computed styles and, when relevant, a CDP screenshot.
- [ ] Bundled, disk/runtime, and effective plugin inventories were kept distinct.

## Pitfalls

- `open` on macOS does not inherit shell exports; use saved connection state or launch the binary with explicit environment, then fully quit before relaunching.
- `/api/status` is commonly public; it cannot prove token correctness, gateway readiness, or WebSocket health.
- Host allowlists and token bypasses are different policies; do not weaken authentication to solve a Host-header error.
- Similar process names do not prove orphaning; use parent trees, cgroups, ports, and start times.
- A generic app name may select a development copy; verify the actual executable path.
- Moving Electron local storage can erase themes, layout, panes, backdrop, and status-bar preferences; back up and merge, never wipe by default.
- A temporary CDP/debug port is a credential and attack-surface risk; close it and verify it is absent after relaunch.

## References and Scripts

- `references/absorbed-source-routing.md` — mandatory routing to original commands and support files when the condensed guide is insufficient.

- `references/connection-and-recovery.md` — consolidated connection, forwarding, host/auth, and recovery depth.
- `references/build-and-ui.md` — consolidated build, theme, plugin, CDP, and renderer depth.
- `scripts/desktop-diagnose.sh` — redacted local connectivity triage.
- `scripts/hermes-v2-launcher.sh` — reversible SSH/remote launcher with dynamic token retrieval.
- `scripts/verify-exact-theme-surfaces.js` — rendered-surface verification for CDP.
