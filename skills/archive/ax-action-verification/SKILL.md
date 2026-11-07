---
name: ax-action-verification
description: "Use when an AX action lands but effect is unverifiable."
version: 1.0.0
author: W.Alter
license: Proprietary
metadata:
  hermes:
    tags: [computer-use, accessibility, ax, verification, smoke-test]
    related_skills: [computer-use, cua-driver-resilience, computer-use-state-verification]
---

# AX Action Verification

## When to Use

Use this class-level skill when a real accessibility action reaches a desktop driver but the backend reports `effect=unverifiable`, or when a Computer Use smoke gate requires proof of an observable mutation without screenshots or vision.

## Core contract

Keep the orchestration boundary explicit:

```text
observe exact window
→ preserve native ref
→ LLM selects one target
→ act(ref)
→ if directly confirmed, finish
→ otherwise one targeted AX readback
→ compare observable state
```

The Hermes LLM remains the strategic authority. Verification is a bounded postcondition check, not a planner, retry engine, label recipe, or second agent.

## Preconditions

Before mutation:

1. Pin the exact current `(pid, window_id)` and require a substantive target.
2. Use the AX snapshot already shown to the LLM; do not take a redundant second “before” observation.
3. Preserve the native `element_token` unchanged through action dispatch.
4. Reject stale-generation refs before driver invocation.
5. Choose a deterministic, reversible control whose effect is observable in AX and does not touch personal content, authentication, payments, permissions, or destructive state.

Off-screen, helper, self-targeted driver, or empty-AX windows are not acceptable smoke targets. A successful `bring_to_front` transport result does not prove that a window moved Spaces or exposes AX; re-check target readiness and fail closed.

## Generic semantic fingerprint

Build a stable multiset or digest from observable AX facts such as:

- role/subrole;
- label/title/description;
- value and scalar state (`selected`, `expanded`, `checked`, `enabled`);
- normalized bounds when geometry is meaningful.

Exclude:

- snapshot IDs and generation counters;
- native ref tokens;
- compact-list indices;
- traversal order unless order is itself the intended observable state.

Those identifiers may change after a fresh capture even when the UI did not. A new token is not proof of a mutation.

`verified=true` requires a real semantic or structural change between the exposed pre-action snapshot and one post-action snapshot. Keep `action_reached_driver` separate from `result_verified`; both are required for a successful smoke.

## One-readback rule

If the backend returns `unverifiable`:

1. Capture AX once against the same exact PID/window.
2. Compare the generic fingerprints.
3. Return `verified=true` only on observable change.
4. If unchanged, return failure/adaptation to the LLM. Do not retry the click automatically.

This one readback is legitimate verification, not free V2 duplication. Screenshots and vision remain zero unless the task explicitly authorizes a visual verification path.

## Smoke-gate evidence

Record the criteria independently:

```json
{
  "real_native_ref": true,
  "action_reached_driver": true,
  "blind_coordinate_click": false,
  "screenshot": 0,
  "vision": 0,
  "result_verified": true
}
```

The aggregate must explicitly require `blind_coordinate_click == false`; do not implement a generic “all values must be true” reducer, because negative safety criteria invert the meaning. Treat the emitted raw proof as authoritative evidence and the aggregate as derived bookkeeping.

## Reversible UI controls

For live validation, prefer toggles or pane controls where AX changes from `Hide …` to `Show …`, or the tree gains/loses a stable region. Do not encode the selected application or label in runtime logic; app/label selection belongs only to the smoke harness or the LLM’s live decision.

If the smoke leaves a persistent layout change, restore it as a separate action and verify restoration independently. A later failed restoration does not erase an earlier valid smoke proof, but the user-facing UI must not be left knowingly altered.

## Tests

Cover at least:

- identical semantics with new generation/token → not verified;
- changed label/value/state/bounds → verified;
- reordered elements with identical multiset → not verified;
- stale token rejected before action;
- `unverifiable` action triggers exactly one targeted readback;
- directly confirmed action does not trigger the extra capture;
- aggregate passes only when coordinates/screenshots/vision remain disallowed as specified.

Run targeted tests after each direct fix. If runtime code changed, run the full relevant suite once after the final code change; do not rerun unrelated live smokes unless the fix could regress them.

## Pitfalls

- **Token-change fallacy:** fresh refs are not UI evidence.
- **Driver-result fallacy:** `ok=true` or `unverifiable` does not prove the postcondition.
- **Double-before capture:** wastes an AX call and can stale the ref just selected by the LLM.
- **App-recipe leakage:** a smoke label must not become runtime routing logic.
- **Off-Space assumption:** activation does not guarantee on-screen/AX-ready state.
- **Boolean aggregate inversion:** safety fields expected to be false need explicit predicates.
- **Proof overwrite:** do not replace a successful evidence artifact with a later cleanup attempt.

## Reference

See `references/minimal-active-smoke.md` for the concise proof schema, fingerprint pseudocode, and replay sequence.
