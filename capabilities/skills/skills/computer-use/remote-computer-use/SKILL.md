---
name: remote-computer-use
description: "Use when a VPS must control a remote Mac GUI safely. Also covers: cua driver resilience; computer use driver wiring."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [computer-use, remote-desktop, macos, ssh, tcc, cua-driver, mcp]
    fallback_for_tools: [computer_use]
    category: devops
    related_skills: [computer-use, mac-computer-use-ssh, ssh-mac-remote-control]
---

# Remote Computer Use

Use this skill when Hermes runs on one host (typically a VPS) but the target
GUI is an interactive macOS session on another host. It covers the transport,
permission identity, driver selection, safety contract, and migration path. It
does not replace the generic `computer-use` action vocabulary or the SSH/tunnel
operations in the Mac-specific skills.

## Core rule

A process on the VPS cannot inherit the Mac user's Accessibility or Screen
Recording grants. Treat the Mac as a **driver host** and Hermes as a **remote
client**:

```text
Hermes VPS
  -> authenticated SSH/Tailscale tunnel
  -> Mac loopback MCP endpoint
  -> permission-owning signed app/host
  -> AXUIElement + ScreenCaptureKit + background input
```

Do not run a local `cua-driver` on the VPS and describe it as Mac control. The
local backend controls the machine where its executable runs.

## First-test gate

Before calling a CuaDriver test an end-to-end Mac test, validate the **target
host**, not only the Hermes VPS:

1. Install/resolve `cua-driver` on the Mac driver host and run its
   `doctor`/`health_report` from the interactive Aqua session. A successful
   VPS-side binary check proves only the local binary and MCP plumbing; it does
   not prove Mac AX, ScreenCaptureKit, TCC, or event injection.
2. Validate the existing transport independently: health response, screenshot
   dimensions/format/latency, and a lightweight content/AX signal. HTTP 200,
   valid PNG bytes, or `ok: true` is not semantic success; a black or empty
   capture must stop the test before vision or mutation.
3. Keep the legacy screen-server path available on its own port while testing
   CuaDriver. Compare read-only health, app/window state, and one harmless
   semantic read before attempting any click or typing.
4. After installing CuaDriver, review its telemetry setting and disable it
   unless the user explicitly opted in. Do not expose installation IDs or
   driver diagnostics as proof of GUI capability.
5. Record the blocker precisely when the target cannot be reached (SSH/Tailscale
   auth, inactive GUI session, TCC, or tunnel), and do not report the test as
   passed. Resume only after the target-side gate is green.

### Scope and live-evidence guard

Treat the user's latest explicit scope correction as a hard boundary. A
computer-use session must not branch into an adjacent repository audit,
feature review, or deployment task merely because related files or stale context
are visible. Stop the unrelated path, reset the task list to the computer-use
workstream, and continue with the target Mac/driver only.

Never carry forward a prior capture verdict as current truth. Re-run the live
health check, screenshot dimensions/format, a lightweight pixel-content metric,
and a scoped AX/window read before calling a capture black, valid, or
production-ready. A valid PNG, HTTP 200, or TCC boolean is not enough.

For standard CuaDriver sessions, read the declared session state before any
mutation. If it reports `desktop_unlocked=false`, `effective_scope="window"`,
`desktop_escalation_required`, or `ax_window_unresolved`, stop before input:
refresh the target/window identity and require an active unlocked GUI session.
Do not force foreground or pixel escalation to work around a locked desktop.

Do not infer live ScreenCaptureKit readiness from `check_permissions
{"prompt": false}`: that read-only form can return
`screen_recording_capturable: null`. A direct probe may require
`prompt: true` and can open macOS consent UI; never trigger that probe silently.

The raw `cua-driver call` CLI and the Hermes wrapper are separate contracts. A
raw action may require explicit `pid` and `window_id` even when an
`element_token` is present; verify the wrapper's action builder before changing
Hermes code. Hermes must capture a fresh target, carry the current
`pid`/`window_id`, and invalidate snapshot tokens after every new capture.

Keep the legacy pixel server as an observational or explicitly approved
fallback only. Never automatically replay an uncertain mutation through the
second driver. After every diagnostic, close named Cua sessions and remove only
the exact temporary captures created by the test; never kill the persistent
CuaDriver or screen-server processes.

See `references/remote-cua-live-diagnostics.md` for the validated read-only
sequence and failure interpretation.

## Remote reachability fallback

A working legacy screen tunnel is not proof that the SSH command route is
usable, and a broken SSH alias is not proof that the Mac is unreachable. When a
configured alias points at `localhost:<forwarded-port>` and returns
`Permission denied (publickey)`, inspect the resolved route with `ssh -G
<alias>` before changing keys or declaring a blocker. Then test the Mac's
Tailscale address directly with the real Mac username and identity:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 \
  -i ~/.ssh/id_ed25519 <mac-user>@<mac-tailscale-ip> \
  'sw_vers; id -u; launchctl print gui/$(id -u) >/dev/null && echo GUI_LAUNCHD=ok'
```

If the direct route succeeds, continue the target-side test over it; do not
stop merely because the convenience alias is stale or points at the wrong local
sshd port. Keep the legacy forward available for comparison, but validate its
health separately from direct remote command access.

### Direct Mac Cua CLI fallback when the Hermes wrapper cannot start

If the Hermes `computer_use` wrapper refuses to start the remote backend (for
example, `walter-cua-remote: remote driver subcommand is not allowed`), do not
fall back to a local Linux driver and do not replay a possibly executed
mutation through the legacy pixel server. Use the already-installed CuaDriver
CLI on the Mac as an explicit, bounded target-side fallback:

1. Validate the direct SSH/Tailscale route and active GUI session.
2. Run the Mac-side `cua-driver status`, `permissions status --json`, and
   `call health_report {}`. Require a running signed daemon, Accessibility,
   Screen Recording, and a passing AX health check before mutation.
3. Call `call list_windows {"on_screen_only":false}` and select the exact
   target `(pid, window_id)` from its current record. Then call
   `get_window_state` with that pair; never reuse a PID/window ID from an old
   capture.
4. If the first AX read returns `ax_window_unresolved`, re-list windows and
   take one fresh `get_window_state` snapshot before escalating. If the fresh
   response contains a coherent screenshot, pixel action is allowed only from
   that same response; otherwise stop and report the live gate failure.
5. After every mutation, take a fresh state read and verify the requested
   postcondition. An unknown completion is never an automatic retry.

This is a bounded Cua route, not permission to bypass the base approval
contract. The validated command sequence and Safari-specific notes are in
`references/remote-cli-fallback-and-safari.md`.

For a Mac without CuaDriver, use the upstream installer from the official
repository, then disable telemetry unless the user explicitly opted in:

```bash
/bin/bash -c "$(/usr/bin/curl -fsSL \
  https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.sh)"
$HOME/.local/bin/cua-driver telemetry disable
```

Launch the signed app daemon from the user's GUI session and poll it rather
than assuming `open` succeeded:

```bash
/usr/bin/open -n -g -a CuaDriver --args serve
$HOME/.local/bin/cua-driver status
$HOME/.local/bin/cua-driver permissions status --json
$HOME/.local/bin/cua-driver call health_report '{}'
```

Prefer this LaunchServices path for a remote test. `launchctl asuser` may be
refused when invoked from an SSH audit session; that shell-level refusal is not
a CuaDriver diagnosis. Never automate clicking TCC permission dialogs. If
Screen Recording is missing, continue with AX-only read checks and report the
visual gate separately.

## Routing decision

1. Use CLI/API/file operations first; do not drive a GUI when a deterministic
   non-GUI route exists.
2. For web-only work, prefer the browser/CDP route and keep the user's browser
   session isolated from scraping.
3. For native Mac apps, use the remote CuaDriver route when the Mac daemon is
   healthy.
4. Keep the legacy W.Alter screen server only as an explicit, temporary
   fallback for pixel-only tasks or migration diagnostics. Never silently retry
   a potentially executed mutation through a second driver.

## Recommended topology

Use a separate Mac port for the new driver, leaving any legacy screen server
port untouched during rollout:

```text
VPS Hermes -> SSH -L <vps-port>:127.0.0.1:<mac-port> -> Mac CuaDriver MCP HTTP
```

The upstream CuaDriver MCP HTTP server is loopback-only. Enable it on the Mac
with a long random bearer token held in the secret scope, then forward the
loopback port through the existing SSH/Tailscale tunnel. Do not bind it to
`0.0.0.0` merely to make the tunnel convenient.

For a zero-code proof of concept, use Hermes' existing `mcp_servers` support:
`url`, `headers.Authorization`, `skip_preflight: true` for a POST-only
endpoint, bounded timeouts, and `tools.include`/`tools.exclude` to keep the raw
Cua surface narrow. Resolve `${ENV_VAR}` from the secret scope rather than
putting the token literally in `config.yaml`. This POC exposes raw MCP tools;
it is useful for validating the Mac host, tunnel, permissions, and upstream
contract, but it should not become the permanent prompt surface.

## macOS permission identity

Use one of these upstream-supported patterns on the Mac:

- standalone `CuaDriver.app` with Accessibility and Screen Recording grants;
- a signed companion app that embeds/hosts CuaDriver and owns both grants.

Do not launch an unidentified raw `cua-driver serve` from an SSH shell,
`open`, an unrelated gateway, or a plain Python LaunchAgent and assume TCC
will attribute permissions to the intended app. LaunchServices can change the
responsible identity; `open` also foregrounds applications, violating the
no-foreground contract. After changing TCC grants, restart the driver daemon
and reconnect the MCP client so the fresh process re-evaluates permissions.

The Mac session must be logged in and available to the GUI subsystem. A remote
driver does not bypass macOS lock/sleep/TCC restrictions. If Accessibility is
missing, stop before mutating. If Screen Recording is missing, use AX-only
operations only when the task can be completed and verified without pixels;
otherwise request the user to grant it.

## Action contract

The remote client must preserve these invariants:

- one Hermes run gets one driver session ID;
- every mutation is serialized per session;
- capture returns the exact app/window target and coordinate basis;
- element refs/tokens are scoped to the newest snapshot;
- stale or ambiguous refs fail closed;
- `ok` means transport/tool completion only, never semantic success;
- consume `effect`, `verified`, `escalation`, `code`, and `completion_known`;
- after `unverifiable`, obtain fresh state before retrying;
- after an unknown remote completion, never replay automatically;
- foreground delivery is a distinct approved escalation, not a prediction;
- record frontmost app before/after when the no-focus contract matters.

Prefer AX actions (`invoke`, `set_value`, `toggle`, `select`, or element-indexed
click) over pixels. Use pixel actions only when the tree is empty, stale, or
known to lie for a canvas/Electron/custom-rendered surface. Use a structured
postcondition (`expect`) where possible instead of trusting a generic screenshot
or `{ok:true}` response.

## Capture-integrity gate before optimization

Validate the pixels before benchmarking a model or dispatching an action. A healthy HTTP response, a valid PNG, or a plausible byte count does **not** prove that Screen Recording captured the desktop. The minimum gate is:

1. call the driver health endpoint;
2. capture one screenshot and record width, height, format, bytes, and latency;
3. inspect a lightweight pixel/content signal (black-pixel ratio or entropy plus a semantic check), not file size alone;
4. require visible application content or a non-empty scoped AX tree;
5. if the frame is black, menu-bar-only, locked, stale, or otherwise ambiguous, mark the capture invalid and **do not call the vision model or mutate the GUI**.

Treat a black capture as a permission/driver/session problem first: check the permission-owning Mac process, Screen Recording/TCC, lock/sleep state, and daemon identity. Do not compensate for invalid pixels by changing models or adding retries.

If System Settings already shows Screen Recording enabled, restart the permission-owning Mac LaunchAgent before resetting TCC or changing the vision model. Use `launchctl kickstart -k gui/$(id -u)/<launch-agent-label>` on the Mac, reconnect the client, and rerun the capture-integrity gate. A long-running process can retain stale TCC state; in the verified legacy W.Alter case, this changed a 2880×1800 ~98 KB black PNG into a 1.85 MB visually complete capture without changing the permission. The detailed diagnostic and acceptance recipe lives in `references/tcc-stale-process-recovery.md`; the legacy screen-server measurement recipe remains in `references/capture-integrity-and-benchmarking.md`.

## Latency/quality routing order

For each task, choose the least expensive reliable rung:

1. CLI/API/file operation;
2. browser/CDP route for web-only work;
3. AX/window-state query for native GUI state;
4. scoped region capture and vision only for unresolved visual ambiguity;
5. full-screen vision and pixel action only as a last resort.

Do not call a slow reasoning model on every passive frame. Gate on state change, reuse a valid observation within its freshness window, crop to the relevant window/region, and reserve the high-quality model for ambiguous or consequential targets. Model benchmarks measure perception latency, not click accuracy; retain a post-action verification step and measure false-success rate separately.

## Coordinate and screenshot rules

Never hard-code Retina `/2`. Coordinate systems vary by capture API, window,
display, scaling, and downsampling. Return capture width/height, native/logical
bounds, target PID/window ID, and scale factors; derive coordinates from that
metadata. Prefer element refs over coordinates entirely.

A modern Cua capture already combines accessibility state and a screenshot in
one response. Re-capture after state-changing actions, but use AX-only or
window-state reads when fresh pixels are unnecessary. Keep screenshots scoped
to the target app/window to reduce leakage and token cost.

## Clipboard and sensitive input

Treat clipboard reads as sensitive data. Use a native driver clipboard operation
when available, snapshot the old clipboard, write only for the bounded action,
verify the read-back/type, and restore it when safe. Never type passwords,
API keys, payment data, or 2FA secrets through a generic computer-use action.
Ask for explicit confirmation immediately before transmitting sensitive data.

## Foreground control approval for legacy pixel actions

When a legacy Mac screen server can physically move the pointer, type, or send keys, treat visible interaction as an explicit foreground escalation. Do not use a fixed blanket lease: bind approval to a `task_id` and keep the lease alive only while that task is active.

Recommended protocol for the W.Alter screen-server fallback:

1. Request `/request-control?task_id=<id>&reason=<human-readable reason>` before the first visible mutation; show the user what will happen.
2. On approval, retain the returned `approval_token` and reuse the same `task_id` and token for the task's visible actions.
3. Send `/control-heartbeat` during long tasks when the action gap can exceed the idle window.
4. Always call `/release-control` in the task cleanup path, including graceful cancellation.
5. Let the server fail closed after inactivity and enforce a hard maximum as a last-resort safety ceiling; never treat the ceiling as the normal task lifetime.
6. Pass `background=1` only for genuinely invisible/background operations. Do not use it merely to avoid asking the user.

The verified W.Alter fallback uses a 60-second inactivity window and a 10-minute hard maximum. These values are safety defaults, not a substitute for explicit release. A new task, a conflicting task, a bad token, or an expired lease must not silently replay the mutation; request approval again or stop. The detailed endpoint contract and verification recipe live in `references/task-bound-foreground-approval.md`.

Before calling the protocol production-ready, test the dialog, heartbeat, and release with a harmless task that performs **no** click/type/key action; then verify `control-status` is closed and capture/health remain functional.

## Remote stdio MCP bridge over SSH

When Hermes runs on the VPS but the signed CuaDriver daemon runs in the Mac GUI session, point `HERMES_CUA_DRIVER_CMD` at an executable wrapper that keeps one SSH stdio channel open for the MCP process. Do not spawn a fresh SSH command per tool call: that adds avoidable latency and breaks the stdio lifecycle.

The wrapper must forward `mcp`, `--help`, and normal driver arguments to the Mac. Intercept `manifest` with a non-zero exit so Hermes uses its local fallback invocation (`wrapper mcp`) instead of trying to execute the manifest's Mac-only absolute path on the VPS. Validate the real Hermes path with `CuaDriverBackend.start()` and repeated calls, measuring one-time MCP startup separately from per-call latency.

Keep the capture-integrity gate mandatory: `permissions status --json` is only a TCC hint; require a real capture with coherent dimensions and a non-black pixel/content signal, plus a scoped AX/window read. Benchmark AX/window-state and full screenshots separately. A legacy route can look faster only because it returns a small black PNG; that is not a valid quality comparison. If the standard session returns `desktop_escalation_required`, `desktop_unlocked=false`, or `ax_window_unresolved`, stop before mutation and require an active/unlocked GUI session rather than forcing foreground or pixel escalation.

See `references/cua-driver-ssh-mcp-bridge.md` for the wrapper and verification recipe.

## Migration from a legacy screen server


Run both paths during migration:

1. prove Mac driver identity and read-only health/permission checks;
2. validate `tools/list`, session start/end, app/window state, and a harmless
   element read through the tunnel;
3. compare background click/type/scroll/drag plus postcondition verification;
4. route the generic Hermes `computer_use` backend to remote Cua;
5. retain the legacy server only as an explicit `legacy_pixel` fallback;
6. remove legacy fallback after real Mac E2E coverage is green.

Do not put side-effecting legacy `GET` calls behind automatic retry logic. A
network timeout after a click is an unknown-completion state, not a no-op.

## Validation matrix

Before calling the remote path production-ready, test on the actual Mac:

- permission granted, denied, and revoked while the daemon is running;
- GUI session active, locked, asleep, and reconnected;
- user typing in another frontmost app while the target is driven;
- AX-native control, Electron/text field, canvas/custom-rendered control;
- drag, modifier click, clipboard Unicode, and multi-display coordinates;
- stale ref after a UI mutation and ambiguous duplicate targets;
- tunnel loss before dispatch, after dispatch, and after completion;
- daemon restart and driver version change;
- prompt injection visible in a page/screenshot and high-risk confirmation;
- proof that focus, Space, and the real OS cursor remain unchanged for the
  background rung.

Record success rate, p50/p95 latency, false-success rate, stale-ref refusals,
focus changes, screenshot bytes/tokens, and recovery time. A green unit suite
on the VPS is not Mac E2E proof.

## Further reading

- `references/cua-driver-macos-direct-validation.md` — validated direct-Tailscale
  smoke test, signed-daemon startup, AX-only probes, and capture-integrity gate.
- `references/remote-mac-cua-http.md` — verified upstream contracts, current
  Hermes integration points, candidate comparison, and POC checklist.
- `computer-use` — generic action vocabulary and background escalation ladder.
- `mac-computer-use-ssh` — existing Mac screen-server skill and TCC history.
- `ssh-mac-remote-control` — SSH/Tailscale tunnel and LaunchAgent operations.

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **remote-computer-use** — CuaDriver / AX capture that is black, partial, stale or wrongly targeted: separate the three contracts, read-only diagnosis, fail-closed capture integrity, window selection by identity.
  Read `references/merged-cua-driver-resilience/remote-computer-use.md` (+ 4 supporting files in that folder).
- **remote-computer-use** — Why Hermes' computer_use driver fails to start: spawn and embedded-daemon contracts, permission_mode, custom/remote driver commands and stdio shims.
  Read `references/merged-computer-use-driver-wiring/remote-computer-use.md` (+ 5 supporting files in that folder).
