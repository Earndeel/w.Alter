# Single `computer_use` front door — Lot 1 contracts

This reference records the reusable contracts and evidence pattern from the
native/AX/Walter front-door implementation. It is deliberately narrower than
the class skill: use it when reviewing or extending a single model-facing
Computer Use surface.

## Runtime contract

Keep one model-facing tool:

```text
computer_use(action="goal", goal="…")
  -> configured backend factory
  -> native launch/URL route
  -> exact PID + native window ID
  -> compact AX observation
  -> AX element action when a target is proven
  -> deterministic postcondition verification
```

The model supplies intent, not transport strategy. Do not expose `ssh`,
`cua-driver`, screenshots, page-vs-pixel choices, or fallback instructions as
goal arguments. The core tool owns approval, dispatch, session lifecycle, and
result shaping; a plugin owns backend policy, target selection, bounded recovery,
and metrics.

## Contract checks

1. **Schema/dispatch:** every schema action has a dispatch handler and every
   dispatch action is represented in the schema. Classify every action as safe
   or approval-gated; keep persistent foreground focus in a separate approval
   scope.
2. **Backend seam:** select a named backend through canonical config and a
   backend-factory registry. A missing/incompatible plugin must return an
   explicit compatibility error; never silently select the built-in backend.
3. **Approval propagation:** the local Computer Use approval callback must call
   the central Hermes approval resolver. An explicit `approvals.mode: off` or
   YOLO decision must skip the local prompt; manual sessions must still prompt.
   Regression-test both paths. Otherwise the request can time out before the
   backend is reached.
4. **Target identity:** require a current PID and native window ID before AX
   observation or mutation. Missing identity is `unverifiable`, not permission
   to guess or use a stale row.
5. **AX evidence:** prefer current element indices or opaque snapshot tokens.
   A fresh capture invalidates prior indices/tokens. An explicit empty AX tree
   is a real negative observation; do not synthesize an actionable element from
   a window title or markdown wrapper.
6. **Verification:** distinguish transport delivery, UI read-back, and the
   requested task postcondition. `effect="confirmed"`/`verified=true` is action
   evidence, not automatically task completion. `window.exists=true` proves
   liveness only; it cannot validate an `unverifiable` click. `unknown` from a
   structured verifier never implies success.
7. **Pixel geometry:** raw coordinates require the newest pixel-bearing capture
   with matching PID, window ID, geometry, and coordinate basis. AX-only refresh,
   target change, failed capture, or stale snapshot clears the geometry/token
   evidence. Never authorize pixels from a remembered screen size.
8. **Bounded recovery:** at most one local retry for a structured
   `suspected_noop` with a driver recommendation for pixel delivery. Do not
   retry `unverifiable` without a fresh semantic check, and do not silently
   escalate to a page or foreground route.

## Compact state and metrics

For non-vision callers, return bounded AX state rather than routing useful
content through auxiliary vision merely because pixels exist. Keep relevant
controls, a bounded page-state marker, total element count, and truncation
metadata. Track independently:

- `model_facing_tool_calls`;
- `logical_backend_calls` and route names;
- screenshots and auxiliary-vision calls;
- verification calls;
- router latency and result size/token estimate.

Backend-call reduction is not a wall-clock benchmark. Report it as fewer
model-visible control rounds unless latency was measured directly.

## Verification recipe

Use hermetic tests for schema/dispatch, backend registration, approval bypass,
AX compaction, stale geometry, capture-integrity envelopes, and the negative
`unverifiable` confirmation case. Run the plugin tests separately from Hermes
core tests so collection or unrelated plugin failures do not hide the relevant
result. Compile changed modules and run `git diff --check`.

For live validation, use two deterministic goals:

- **Positive:** launch an explicitly named native app, resolve its exact window,
  and observe it through AX. Record real route names and latency.
- **Negative:** request a target that is not present in the current AX state.
  Return `needs_user_input` or `unverifiable`; never invent a click based on a
  label, URL, or presumed first result.

A useful evidence tuple is:

```json
{
  "model_facing_tool_calls": 1,
  "logical_backend_calls": 2,
  "routes": ["native.launch_app", "AX.observe"],
  "screenshots": 0,
  "vision_calls": 0,
  "verification_calls": 0,
  "latency_ms": "measured"
}
```

The values above are a shape, not defaults; replace them with actual output.
Separate software-contract tests from live Mac/TCC/AX evidence, and label a
dirty worktree as non-release-certified.

## Known integration pitfall

A nested Computer Use callback can drift from Hermes' central approval state.
The symptom is an approval timeout even though `--yolo` or
`approvals.mode: off` is active. The durable fix is not to disable approval in
the tool: make the callback consult the central bypass resolver and add a
regression test proving the explicit bypass reaches it.
