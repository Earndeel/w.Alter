# Remote Cua live diagnostics

This reference records the reusable validation pattern for a VPS controlling a
signed CuaDriver daemon and a legacy pixel screen server on a remote Mac. It is
not a claim that any one capture verdict remains true across sessions.

## Read-only target gate

1. Reach the Mac through the authenticated direct route (Tailscale SSH when a
   convenience alias is suspect). Confirm the GUI user, the signed CuaDriver
   daemon, and the loopback ports independently.
2. Query CuaDriver `health_report` and record the live driver identity,
   executable/bundle, AX status, Screen Recording status, and version.
3. Query `check_permissions` with `{"prompt": false}`. Treat the booleans as
   TCC identity evidence only. A read-only response may legitimately report
   `screen_recording_capturable: null` and `direct_capture_status: not_checked`.
   Do not run the prompt-capable direct probe without explicit user approval:
   it can open macOS consent UI.
4. Start a named Cua session with `capture_scope: "auto"`, then read
   `get_session_state`. The mutation gate is closed when
   `desktop_unlocked=false`, `effective_scope="window"`,
   `desktop_escalation_required`, or `ax_window_unresolved` is present.
5. Read `list_windows`, `get_accessibility_tree`, and one exact target window
   state. Window IDs and AX snapshots are live data; never reuse an old pair or
   old element ref after the visible surface changes.

## Capture-integrity comparison

For each driver, capture at the same time and record dimensions, format, byte
count, and a lightweight pixel signal (for example, non-black ratio, mean
luminance, and a coarse grid). File size and HTTP success alone are not proof.
A frame that is black, menu-bar-only, locked, stale, or otherwise ambiguous
must not be sent to vision and must not drive input.

CuaDriver `get_desktop_state` can return `screenshot_png_b64` in the JSON
response. Some daemon builds reject a temporary `screenshot_out_file` path with
a path-scope error even when the path looks valid. The reliable diagnostic
fallback is to call without the output-path argument, parse the JSON on the
Mac, decode `screenshot_png_b64` (or `png_b64`) to a test-only file, calculate
stats there, and delete it afterward. Do not paste the base64 into the chat.

The legacy W.Alter screen server is passive at `/health`, `/control-status`,
and `/screenshot`. `/health` should expose the approval gate and task-bound
control model; `/control-status` must be closed before any test. A healthy
legacy screenshot proves only that its LaunchAgent can capture pixels; it does
not prove AX semantics or justify an input action.

Do not compare against remembered numbers from an earlier run. A previously
black v7 capture can become valid after a daemon/session change, and CuaDriver
and v7 may observe different surfaces while the Mac is locked or changing
Spaces. Re-run the gate and report the current measurements.

## AX action proof

Use the Hermes wrapper for a real action, not a hand-written raw CLI call. The
raw `cua-driver call` surface may require explicit `pid` and `window_id` even
when an `element_token` is supplied; this is a CLI contract quirk, not proof
that the Hermes backend is wrong. The wrapper should derive the pair from a
fresh capture, attach the current snapshot token, and disarm the target when a
capture fails.

For a harmless reversible test: capture a non-critical AX control, record its
state, perform one background action, take a fresh state snapshot, verify the
postcondition, then restore and verify again. If the session reports locked or
AX-unresolved, stop before the action and record the blocker; do not force
foreground delivery or retry the same mutation through the pixel server.

After an uncertain remote completion, never replay automatically through a
second driver. Obtain fresh state or ask for the user-approved next rung.

## Acceptance evidence shape: native Mac AX + pixels

A successful live validation on 2026-08-06 established the following reusable
proof pattern. The exact app/window IDs and labels are session data; preserve
the evidence relationships, not those literals:

1. Query the signed Mac CuaDriver daemon's permission status. Accessibility and
   Screen Recording being `true` are TCC identity evidence only; a
   `screen_recording_capturable: null` / `not_checked` field remains unproven
   until a real scoped `get_window_state` capture succeeds.
2. Call `list_windows(on_screen_only=true)` and reject the driver's own window
   plus thin helper/title-bar surfaces. Prefer the substantive main application
   window using its live `(pid, window_id)` and meaningful bounds.
3. Call `get_window_state` for that exact pair and require both a structured AX
   tree and `screenshot_frame_valid: true`. Record the returned screenshot
   dimensions/scale, but do not infer coordinate transforms from scale alone.
4. Query one harmless reversible AX control on a fresh snapshot. Address it
   with its current `element_token` (and the raw CLI's required `pid`,
   `window_id`, and matching snapshot data), then perform the background AX
   action. `effect: "unverifiable"` means the action was delivered but must be
   verified; it is not permission to retry.
5. Re-capture and verify a semantic transition, not merely a fresh PNG. The
   validated example changed a checkbox label/value from `Mute haptics`/`0` to
   `Unmute haptics`/`1`, then used a new token to restore it to
   `Mute haptics`/`0`. This proves AX dispatch, state readback, token refresh,
   and restoration in one bounded test.
6. End the named session and delete only the exact temporary captures.

This acceptance pattern is stronger than HTTP 200, a non-empty AX payload, a
TCC boolean, or an action response without a postcondition. It also keeps a
legacy pixel server from becoming an automatic retry path.

## Cleanup and scope

End every named diagnostic Cua session, remove only the exact temporary image
files created by the test, and leave persistent CuaDriver/screen-server
processes alone. Keep the task scoped to Computer Use: do not pivot into a
nearby repository audit or deployment review because stale context mentions
another project. Existing repository changes are evidence to inspect, not a
reason to edit them during a GUI validation run.
