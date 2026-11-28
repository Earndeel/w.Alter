# Minimal Active Operator loop — validated vertical-slice notes

## Reusable contract

Keep one model-facing front door: `computer_use(goal=...)`. The Hermes LLM remains the sole strategy authority. The runtime may execute one atomic capability, or return observation/capability state for the LLM to choose the next primitive; it must not hide a multi-step application recipe.

```text
goal
  -> one atomic launch/open-url operation, OR
  -> AX observation + compact native refs
  -> return to Hermes LLM
  -> one selected action
  -> minimum targeted verification
  -> continue, adapt, or finish
```

Allowed internal atomics can include `launch_app`, `focus_app`, `open_url`, AX invoke/click, text input, and key/hotkey. Do not turn them into an internal planner that selects and chains unrelated controls.

## Snapshot-bound native refs

A numeric element index can be dangerous when the backend silently associates it with the newest cache: after a new capture, the same index may identify a different element. Bind action authority to the exact AX snapshot exposed to the LLM:

1. When producing compact AX state, retain each opaque native token and derive an exposed snapshot identity from the complete reliable-token set.
2. Arm the backend with the exposed snapshot/token map.
3. Any later capture supersedes and disarms that authority.
4. Consume an armed ref at most once for an action.
5. If the ref is stale, unknown, or superseded, reject locally before driver dispatch with `adaptation_required=true`, `failure_reason=stale_ref`, `next_authority=llm`, and no automatic retry.

This guard was validated live: a second `get_window_state` changed the generation, then the old element index was rejected as `stale_element_token`; no `click` RPC followed.

## Compact AX projection

Large macOS AX trees often enumerate zero-bounds global/menu items before visible window controls. Keep true native refs and generic roles, but order controls with non-zero width and height before zero-bounds entries. Preserve stable order within each group. Compute stale/snapshot identity from the complete reliable-token set, not only the truncated model-facing slice.

This is generic observation shaping, not target selection: the runtime still must not pick `Reload`, a video, a tab, or any other application-specific target for the LLM.

## Result semantics

Separate:

- `confirmed`: sufficient driver/read-back evidence for that action;
- `unverifiable`: input may have landed, but the LLM needs targeted inspection;
- stale/ref unavailable: no action dispatched, `adaptation_required=true`;
- L2/destructive/security-sensitive intent: fail closed with `needs_confirmation` before device RPC.

A native launch response proving `process_running/requested` confirms dispatch and app presence, not automatically a loaded URL or broader user-goal postcondition. Use the cheapest native read-back that proves the stated requirement; do not manufacture success from request acceptance.

## Minimal smoke gate

Use one functional run plus a few stability repetitions, not certification-scale benchmarking:

- A: launch;
- B: native URL navigation with an appropriate native postcondition;
- C: live AX observation → real native ref → action → targeted verification;
- D: unavailable/stale target → no blind action and `adaptation_required=true`.

Record model-facing calls, Computer Use calls, device RPC names/counts, AX captures, screenshots, vision calls, total time, Operator time, and result. Reuse one backend/session when the test is specifically proving no duplicate device acquisition; otherwise keep independent smoke isolation explicit.

Hard stop only when existing tests are green, all four live smokes pass, and one targeted architecture/regression review returns `must_fix=[]`. An executed AX action whose effect remains `unverifiable` is not a passing C smoke until the targeted postcondition is read back. Put non-blocking findings in the backlog; do not reopen earlier certified lots.