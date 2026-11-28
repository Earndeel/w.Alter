# Live AX validation reference

Sanitized notes from a real Hermes/macOS validation. This is a reusable
verification record, not a claim that every app exposes the same AX surface.

## Target and preflight

- Use a fresh disposable session ID.
- Select the substantive Hermes window from `list_windows`: exact `(pid,
  window_id)`, on-screen, normal content dimensions. Ignore the 24/44-pixel
  chrome rows and the CuaDriver window.
- `get_window_state` returned a valid pixel frame and a fresh snapshot with
  controls such as `Hide sidebar`, `Hide right sidebar`, and `Mute haptics`.

## Mutation recipe

1. Read a fresh snapshot and retain its `snapshot_id` plus the target's
   `element_token`.
2. For CuaDriver 0.17, send either `element_token` or
   `element_index + snapshot_id`; a bare index is refused.
3. Start with `delivery_mode: "background"` for a harmless control.
4. If the response is `effect: "unverifiable"`, read the target again before
   retrying. If the expected label/value is unchanged, retry the same action
   once with `delivery_mode: "foreground"`.
5. Verify by read-back, not by the dispatch response. In the Hermes test,
   `Hide sidebar` changed to `Show sidebar` after foreground escalation.
6. Reacquire the snapshot after every mutation. The right-sidebar action
   changed `Hide right sidebar` to `Show right sidebar`; the other sidebar's
   visibility also needed read-back rather than assumption.
7. Restore with the current token for the `Show ...` control and verify both
   final labels are back to `Hide ...`.

## Disposable-app readiness guard

`launch_app` can acknowledge a process while returning `window_ready: false` and
an empty `windows` list. Use a bounded readiness poll over `list_windows`, then
require an on-screen substantive window and a resolved AX tree. An
`activated: true` response from `bring_to_front` is not enough if the window
remains off-screen or `get_window_state` returns `ax_window_unresolved`.
Fail closed, use the app's native quit path when the probe was ours, call
`end_session`, and restore the prior app. Do not fall back to guessed pixels or
claim an interaction that was not read back.

## Cleanup checklist

- Confirm the harmless UI state is restored with a fresh AX snapshot.
- Call `end_session` even after an aborted probe.
- Confirm the disposable app is no longer running and the intended app is
  active.
- Do not retain screenshots, private text, credentials, or raw session data in
  this reference.
