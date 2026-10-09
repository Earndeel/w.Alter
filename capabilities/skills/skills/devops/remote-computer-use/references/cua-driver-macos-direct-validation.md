# CuaDriver Mac direct validation

Use this recipe when Hermes runs on a VPS and the CuaDriver target is an
interactive Mac reachable over Tailscale. It is a read-first smoke test; it
never clicks TCC dialogs and does not mutate a personal browser session.

## 1. Prove the route, not the alias

A legacy port forward can be healthy while an SSH convenience alias points at
the wrong local `sshd`. Resolve the alias before changing credentials:

```bash
ssh -G <alias> | grep -E '^(hostname|port|user|identityfile|proxycommand) '
```

Then test the Mac directly over its Tailscale address:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=8 \
  -i ~/.ssh/id_ed25519 <mac-user>@<mac-tailscale-ip> \
  'sw_vers; id -u; launchctl print gui/$(id -u) >/dev/null && echo GUI_LAUNCHD=ok'
```

A direct success is enough to continue. Do not treat a stale alias failure as
an unavailable Mac, and do not confuse a legacy screen-server `/health` result
with remote command access.

## 2. Install on the Mac driver host

Run the official upstream installer remotely only after the direct route is
proven:

```bash
/bin/bash -c "$(/usr/bin/curl -fsSL \
  https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.sh)"
$HOME/.local/bin/cua-driver telemetry disable
```

The Mac-side signed bundle is the permission-owning identity. Do not use the
VPS-installed Linux binary as evidence of Mac capability.

## 3. Start and inspect the signed daemon

Use LaunchServices and poll; do not assume that a successful `open` means the
daemon is ready:

```bash
D="$HOME/.local/bin/cua-driver"
/usr/bin/open -n -g -a CuaDriver --args serve
$D status
$D permissions status --json
$D call health_report '{}'
```

`launchctl asuser` can be refused when invoked from an SSH audit session. That
shell error is not a CuaDriver health result; use the signed app path above.

Never automate clicking macOS Accessibility or Screen Recording permission
dialogs. If Screen Recording is absent, keep the test AX-only and report the
visual gate as incomplete.

## 4. Read-only AX probes

With the daemon running, these calls validate the semantic branch without
stealing focus:

```bash
$D call get_screen_size '{}'
$D call list_apps '{}'
$D call get_accessibility_tree '{}'
```

A useful AX result includes the logical display size, running app metadata, and
visible window records. This proves target-host AX reachability, not visual
capture or successful mutation.

For a harmless app test, launch a neutral app such as Calculator:

```bash
$D call launch_app '{"bundle_id":"com.apple.calculator","creates_new_application_instance":true}'
$D call list_windows '{}'
```

Keep the app backgrounded. If it returns `process_running: true` but
`window_ready: false`, or if `get_window_state` returns
`ax_window_unresolved` with `recommended: px`, do not foreground it merely to
force a green test. That is a useful background-window result; foreground is a
separate explicit escalation.

## 5. Capture-integrity gate

A valid PNG header, dimensions, or non-zero byte count is not enough. Capture
one frame and inspect actual pixels/content:

```bash
$D call get_desktop_state '{}' \
  --screenshot-out-file /tmp/cua-driver-desktop.png
scp <mac-user>@<mac-tailscale-ip>:/tmp/cua-driver-desktop.png /tmp/
```

If the frame is all black, menu-bar-only, locked, or otherwise ambiguous, stop
before vision or mutation. Re-check the daemon's own TCC identity and
`screen_recording` status. A typical degraded-but-useful state is:

- `tcc_accessibility: pass`;
- `tcc_screen_recording: fail`;
- `ax_capability: pass`;
- `screen_capture_capability: skip` or a black screenshot.

In that state, keep AX/window-state checks, use CDP for web-only work when
appropriate, and wait for the user to grant Screen Recording before claiming
full Computer Use E2E.

## Acceptance criteria

Do not call the Mac test fully green until all of these are true:

- direct Tailscale SSH route and interactive GUI session are verified;
- CuaDriver daemon status is running under the signed Mac identity;
- Accessibility is granted and an AX read succeeds;
- Screen Recording is granted and a scoped capture contains real pixels;
- one harmless action is followed by a fresh postcondition read;
- no unapproved focus change or personal browser mutation occurred;
- telemetry state matches the user's opt-in choice.
