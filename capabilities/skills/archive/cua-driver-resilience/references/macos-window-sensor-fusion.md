# macOS Window Sensor Fusion

Use this reference when a macOS app appears to be running or visible but accessibility/window enumeration disagrees.

## Contract

Treat window state as independent facts, not a single `usable_window` gate: process (`process_running`, `pid`); native window/surface (`window_exists`, `window_source`, `window_id`, `bounds`); state (`window_on_active_display`, `window_visible`, `window_frontmost`, `window_minimized`, `window_hidden`); capabilities (`native_targetable`, `ax_accessible`, `pixel_accessible`); and provenance (`observation_sources`, `freshness`). If native/WindowServer evidence says a surface exists while AX returns no windows, return `window_exists=true` and `ax_accessible=false`; never collapse it into `no_window`.

## Evidence semantics

- WindowServer/native enumeration proves existence, identity, geometry, and only the visibility/order facts it reports.
- Process/NSWorkspace/user-presence facts prove process state, PID, and foreground/activation state.
- AX proves semantic controls, roles, text, and AX references only.
- Pixels/vision prove visual state and support coordinate interaction only with current pixel evidence.

Do not let one source invalidate another or report a capability without fresh evidence.

## Action-specific targetability

Require only evidence needed by the current action: launch needs process/native evidence when available; focus/activate needs activation/frontmost or native process/window evidence (AX is not mandatory); move/restore needs native identity plus geometry; AX click/type needs current AX accessibility/ref; visual click/capture needs pixel evidence; key/type needs suitable focused process/window evidence; AX capture needs AX accessibility. A background window is still a real window: `window_frontmost=false` is neither nonexistence nor a reason to steal focus.

## Idempotent launch and bounded recovery

If the process is running and a native/window surface is observed, do not launch again merely because AX is empty or a secondary verification failed. Launch once, use a few short bounded readiness polls to refresh state, and return fresh post-action facts. Recovery may enumerate background/off-screen candidates, identify exact PID/window, restore/reposition mechanically when supported, activate exactly once only when requested, then re-observe only the needed facts. Bound all polls/retries. Failed recovery must preserve `ax_accessible=false` instead of rewriting it as `window_exists=false`.

## Post-action and verification boundary

State-changing actions should return compact fresh `post_action` facts covering process, native window, foreground, AX/pixel capabilities, bounds, source, and timestamps. Hermes decides the next action and completion; Operator does not. Unit tests prove the contract but not a live macOS E2E, so run the bounded micro-smoke and fresh-session E2E before deployment and report external driver/permission limits honestly.
