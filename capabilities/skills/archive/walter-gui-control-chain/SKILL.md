---
name: walter-gui-control-chain
description: Use when Monsieur needs a GUI task coordinated across Walter Operator, background desktop control, and a remote Mac session, with each layer handing verified state to the next.
type: workflow
requires: [walter-computer-use, computer-use, remote-computer-use]
---

# Walter GUI Control Chain

Use this workflow when a real session requires all three W.Alter GUI skills in sequence. The workflow preserves one planning authority, passes only verified observations between stages, and stops when a gate fails or the requested task is complete.

Hermes remains the planner throughout. Each sub-skill performs only the work assigned to its stage and returns compact facts, current target identity, action results, and unresolved blockers.

## Chain

```text
Walter Operator
    ↓ verified local or reachable GUI state
Background computer use
    ↓ verified desktop result and remote-control requirement
Remote computer use
    ↓ verified target-Mac result
Hermes final postcondition check
```

## Entry conditions

Start this chain only when all of the following apply:

- The task requires GUI inspection or manipulation rather than a deterministic CLI, API, browser-content, or file operation.
- The session begins with a Walter Operator surface or needs its device-aware observation and atomic-action contract.
- The task then requires background desktop control through the generic `computer_use` action vocabulary.
- The final stage must inspect or control a GUI session on a remote Mac from a VPS or other remote Hermes host.

If any stage is unnecessary, use the applicable sub-skill directly instead of forcing the chain. A later stage must not compensate for a failed earlier gate.

## Step 1 — Walter Operator

Before doing this step, load `walter-computer-use` with `skill_read`.

Use Walter Operator to establish the initial GUI facts and perform any authorized atomic setup needed by the task. Observe the relevant app, window, dialog, device, or file-picker surface before acting. Keep Hermes responsible for interpreting the user goal and choosing actions.

The handoff to Step 2 must contain:

- the current device/session identity and transport, when relevant;
- the target app or window and its observed identity;
- the current UI state, including unexpected dialogs, permission surfaces, or errors;
- the exact atomic action result and its post-action verification;
- any capability limits, stale references, or unresolved effects;
- the remaining task intent expressed as a concrete postcondition.

Do not hand off on an assumed success. If a permission, password, payment, destructive-confirmation, or other gated surface appears, stop at this stage and return the observation for Hermes to resolve under the applicable authorization rules.

### Gate 1

Proceed only if the target is identified, the latest observation is fresh, and the initial action's local effect is confirmed or explicitly classified as unresolved with a safe next observation. Invalidate consumed UI references after a state-changing action.

## Step 2 — Background desktop control

Before doing this step, load `computer-use` with `skill_read`.

Translate the Step 1 handoff into the generic `computer_use(action=...)` vocabulary. Capture the scoped target first, use current element indices or coordinates from that capture, and verify every state-changing action. Keep delivery background-first and use the returned effect, verification, code, and escalation fields to decide whether another observation or an approved escalation is warranted.

The handoff to Step 3 must contain:

- the fresh target app/window identity and capture generation;
- the verified desktop state after Step 1 and any actions in this stage;
- the exact remote-control requirement, including target Mac, session, and intended postcondition;
- the action verdicts and any escalation already used;
- whether the browser surface is chrome or page content, so the next stage does not use the wrong toolset;
- unresolved dialogs, permissions, focus changes, stale references, or unknown completion states.

Never treat a transport success, screenshot, or generic `{ok:true}` as semantic completion. If an action is unverifiable, recapture before retrying. If completion remains unknown after the fresh read, do not replay the mutation or pass it forward as successful.

### Gate 2

Proceed only if the desktop state is coherent and the remote stage has a specific target and postcondition. The target must not be a personal or sensitive browser surface unless it is part of the user's explicit task. Do not request foreground delivery merely because an app is known to need it; use it only in response to a live driver signal and the applicable focus-change approval.

## Step 3 — Remote Mac control

Before doing this step, load `remote-computer-use` with `skill_read`.

Treat the Mac as the permission-owning driver host and Hermes as the remote client. Validate the target route, active interactive GUI session, driver health, permission state, and capture integrity on the Mac before mutation. Preserve the existing transport as an observational fallback only; never automatically replay an uncertain mutation through a second driver.

Use a fresh target/window listing and carry the current target identity into the capture and action. Confirm that the capture contains meaningful application content or a coherent scoped accessibility tree. A valid HTTP response, PNG, or permission boolean alone does not pass this gate.

For each remote mutation:

1. Capture the current target and invalidate older element references.
2. Prefer an accessibility action when the target is exposed reliably.
3. Use pixels only when the current capture establishes that the surface requires them.
4. Consume the structured action verdict.
5. Obtain fresh state after an unverifiable or unknown result before deciding what to do.
6. Verify the requested postcondition on the target Mac.

Stop before input if the desktop is locked, the window cannot be resolved, the target session is inactive, capture integrity fails, Accessibility is unavailable, or Screen Recording is required but unavailable. Do not silently trigger consent UI or bypass the Mac's permission identity.

### Final gate

The workflow is complete only when a fresh remote observation verifies the requested postcondition and the result is attributable to the intended app/window on the intended Mac session. Return the final facts to Hermes, including the target identity, verification evidence, and any remaining limitation. If the postcondition cannot be verified, report the state as unresolved and do not claim completion.

## Handoff contract

Every handoff is a structured observation, not a narrative assumption:

```text
{
  target: {host, session, app, pid, window_id},
  observation: {freshness, state, accessibility, visual_integrity},
  action: {operation, effect, verified, code, completion_known},
  postcondition: {requested, verified},
  blockers: []
}
```

Omit unavailable fields rather than inventing them. A later stage may refresh any field, but it must not reuse stale target identities, element references, screenshots, or completion claims.
