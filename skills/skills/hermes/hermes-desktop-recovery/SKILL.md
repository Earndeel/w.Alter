---
name: hermes-desktop-recovery
description: "Recovery patterns when Hermes V2 Mac desktop app fails to connect — ECONNREFUSED, timeout, or gateway errors after dashboard restart. Also covers: hermes desktop setup; hermes remote connection; hermes desktop host header pitfall."
category: devops
tags: [hermes, desktop, recovery, connectivity]
related_skills: [hermes-desktop-tailscale, hermes-desktop-setup, hermes-desktop-debug]
---

# Hermes Desktop Recovery

Operational recovery patterns for the Hermes V2 Mac Electron app when it fails to connect after a server-side restart or configuration change.

## First decision: server path or Mac client state

Do not assume that `Gateway needs setup` means the VM gateway is stopped. First verify the remote dashboard and gateway status, then test the same URL from the Mac. If REST and WebSocket work from the Mac but the app still reports setup/offline, inspect the Mac-side connection contract before changing the VM again.

The preferred remote path is a Tailscale-only forward to the loopback dashboard, with session-token authentication kept enabled. For a reachable Mac, SSH over its Tailscale address is the fastest reversible way to inspect and repair the client; redact tokens in all output.

## Validated Mac-side recovery workflow

1. Confirm Tailscale reachability and SSH with `BatchMode`; do not use blind `pkill` or kill every matching process. Gracefully quit Hermes with AppleScript, and inspect process paths if duplicate app copies exist.
2. Inspect `~/Library/Application Support/Hermes/connection.json` and `launchctl getenv HERMES_DESKTOP_REMOTE_URL` / `HERMES_DESKTOP_REMOTE_TOKEN`, never printing token values.
3. For the current Electron contract, keep `mode` set to `remote` and point the selected saved connection at the supervised local relay (`127.0.0.1:9119`), with the live dashboard session token. Treat `connection.json` / the selected entry in `connections.json` as authoritative; set `launchctl` variables only for an intentional environment-only configuration, never as a stale override. Back up the connection file before editing.
4. Launch the intended bundle by absolute path (for example `/Applications/Hermes V2.app`), not by a generic app name when a development copy may also be registered. Verify the running process path.
5. If the app logs `Remote Hermes backend is ready` but the window is black or remains in setup, first make a timestamped copy of `Local Storage` and inspect it. Electron `Local Storage` is not renderer cache only: it contains user themes, injected CSS, selected theme/mode, layout trees, pane states, zoom, backdrop, and status-bar preferences. Moving it without preserving those records makes the desktop appear to lose all customization. If it must be moved for renderer recovery, keep the copy, and restore/merge the appearance records afterward (at minimum `hermes-desktop-user-themes-v1`, `hermes-desktop-theme-v2`, `hermes-desktop-profile-themes-v1`, `hermes-desktop-mode-v1`, `hermes-desktop-profile-modes-v1`, plus `hermes.desktop.layoutTree.v2`, `hermes.desktop.paneStates.v1`, `hermes.desktop.statusbarHidden`, `hermes.desktop.backdrop.v1`, and zoom/translucency keys). Do not touch Cookies, session databases, or `connection.json`.
6. Validate the app after a normal relaunch. If native macOS screenshots look black while the app is suspected to be loaded, use a temporary local CDP launch (`--remote-debugging-port`) to inspect DOM/text and capture a Chromium screenshot, then close and relaunch without debug flags. The diagnostic port must not be left open.

A session-specific reproduction and verification recipe is in `references/remote-config-and-renderer-recovery.md`.

## Three failure modes (ordered by frequency)

### 1. ECONNREFUSED

The forwarder between the Tailscale interface and the loopback dashboard process died. The desktop app gets an immediate rejection — not a timeout, not a 401.

**Check**: is the forward process listening on the Tailscale IP? Use `ss` or `netstat` on the server.

**Fix**: restart the owning service or forward. If the forward is ad-hoc, inspect which PID owns the port and stop only the known forward gracefully before re-launching; do not use a blanket process kill. A supervised service with `Restart=always` prevents recurrence. The forward must bind the specific Tailscale IP, which requires root-level supervision (not user-level).

### 2. Timeout (backend did not become ready)

The forward is alive (ECONNREFUSED would fire otherwise), the dashboard responds to direct queries, but the Electron app hangs on `waitForHermes` and times out after ~45 seconds.

**Check**: verify the exact URL selected by the Mac connection file, not merely a server-side curl. Run the authenticated REST and WebSocket probes from the Mac and hold the WebSocket idle beyond the suspected relay timeout. If it closes at a repeatable interval while short HTTP calls succeed, inspect the relay for a connect timeout retained on later `recv()` calls before touching Electron state.

**Fix**: repair the relay first (a Python relay must clear its bounded connect timeout with `upstream.settimeout(None)` after connection and use blocking full-duplex semantics). Only if the authenticated WebSocket and the complete Desktop liveness window pass while the UI still fails, quit Hermes and move the renderer-state directories to a timestamped backup, then relaunch:

- `~/Library/Application Support/Hermes/Local Storage`
- `~/Library/Application Support/Hermes/Session Storage`
- `~/Library/Application Support/Hermes/Cache`
- `~/Library/Application Support/Hermes/GPUCache`
- `~/Library/Application Support/Hermes/Code Cache`

If a separate `~/Library/Caches/Hermes` directory is present, it can be included in the same reversible backup. Do not delete or reset Cookies, session databases, or the connection file. This resolves persistent renderer state corruption that survives normal app restarts while preserving the remote token and user sessions.

### 3. Gateway setup/offline state

The desktop label is ambiguous. A stopped remote gateway is only one possibility; a Mac connection file left in `mode: local`, a missing `HERMES_DESKTOP_REMOTE_TOKEN`, or a stale renderer can produce the same UI.

**Check**: query the remote dashboard status endpoint with the session token. If it reports `gateway_state: stopped`, restart the gateway process and wait for platform connections to re-establish. If it reports `gateway_state: running` and the Mac can reach REST/WebSocket, repair the Mac connection config and renderer state instead of restarting the VM repeatedly.

**Verify**: the remote status endpoint, a token-authenticated REST request, and a WebSocket handshake must all pass from the Mac before declaring the gateway path healthy.

## Pitfalls

- **Host header rejection after a dashboard update**: the opt-in variable is `HERMES_DASHBOARD_ACCEPTED_HOSTS`, not `_TAILSCALE_ACCEPTED_HOSTS`. Configure the exact Tailscale IP and MagicDNS names used by the forwarder (for example `100.91.35.121,w-alter,w-alter.tail32cf1c.ts.net`). Test both the forwarded URL and the loopback service; a request with a bad Host must remain rejected.
- **Forward fragility**: the forwarder is single-point-of-failure. Without supervision, every dashboard restart breaks the desktop app.
- **Cache persistence**: Electron cache survives app reinstalls. “It works from curl but not the app” → verify the Mac connection contract, then move renderer caches before deeper network debugging.
- **Gateway silence**: a stopped gateway shows no visible error in the desktop app UI. Always check the dashboard status endpoint after a restart.
- **Stale forward/app instances**: inspect ownership, PIDs, and bundle paths first. Prefer graceful service/app restarts; never kill all matching processes blindly, especially when one may be a user session or the supervised forward.


## Headless backend after retiring the web dashboard (verified 2026-10-17)

The Mac application still needs the Hermes API backend even when Monsieur has retired the browser dashboard. If Mac 127.0.0.1:9119 listens but its target 100.91.35.121:8788 refuses connections, check the VM units before resetting the app or its themes. Current deployment: hermes-desktop-backend.service runs the official `hermes serve --host 127.0.0.1 --port 8787` (headless; no dashboard SPA), and hermes-desktop-tailscale.service forwards ONLY 100.91.35.121:8788 to that loopback backend. Both are systemd-enabled. The legacy hermes-dashboard and hermes-socat-ts units remain retired; no public Cloudflare route is needed.

Keep the existing Mac connection and token. VM authentication is loaded from /root/.hermes/desktop-backend.env (0600 EnvironmentFile), never inline in a unit and never printed. Backup before changing units/config. Monsieur explicitly authorized this private backend restoration on 2026-10-17; do not infer permission for additional public listeners or unrelated account changes.

Verify from the Mac: /api/status returns 200, /api/sessions?limit=1 returns 401 without a token and 200 with the existing connection token in a header (do not print session content). An arbitrary Host must remain rejected (400). Relaunch the exact /Applications/Hermes V2.app gracefully when needed; ~/.hermes/logs/desktop.log must report `Remote Hermes backend is ready` without repeated boot failures. Preserve conversations, Cookies, Local Storage and appearance settings. The 2026-10-17 repair passed those checks after normal quit/relaunch.

Before retiring a service, map its Desktop/API dependants: removing the browser UI must not silently remove the backend the Mac depends on. Include both units, the protected env file and the Mac relay contract in module/integration backup coverage. The older Host-header notes elsewhere in this skill are version-specific; inspect current source rather than relying on an environment allowlist.

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **hermes-desktop-setup** — Desktop app → remote server connection chain: token mismatch, environment variable injection, forwarding.
  Read `references/merged-hermes-desktop-setup/hermes-desktop-setup.md` (+ 1 supporting file in that folder).
- **hermes-remote-connection** — ECONNREFUSED 127.0.0.1:9119 from the desktop or TUI client: port architecture, SSH mode, Tailscale direct, legacy SSH tunnel, attach mode, token auth.
  Read `references/merged-hermes-remote-connection/hermes-remote-connection.md` (+ 4 supporting files in that folder).
- **hermes-desktop-host-header-pitfall** — `400: Invalid Host header` after the v0.18.2 update, the WebSocket 403 on the chat tab, stale dashboard processes.
  Read `references/merged-hermes-desktop-host-header-pitfall/hermes-desktop-host-header-pitfall.md` (+ 1 supporting file in that folder).
