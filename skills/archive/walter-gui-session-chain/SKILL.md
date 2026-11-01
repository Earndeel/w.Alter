---
name: walter-gui-session-chain
description: Use when Monsieur's GUI task requires the Walter Operator, background desktop control, and a remote Mac session in sequence.
type: workflow
requires: [walter-computer-use, computer-use, remote-computer-use]
---

# Walter GUI Session Chain

Use this workflow when a task spans the three W.Alter GUI capabilities in the established order:

1. Walter Operator establishes the observed GUI context and performs or verifies the local or directly addressed device interaction.
2. Computer Use continues with background-first desktop control, using the verified state from Walter Operator.
3. Remote Computer Use handles the VPS-to-Mac path when the remaining work belongs to an interactive remote Mac GUI session.

Do not enter a later step until the preceding step has returned a usable, current handoff. A handoff contains only observed facts needed by the next step: target device or host, application and window identity, relevant state, completed actions, verification evidence, unresolved dialogs or permissions, and any safety boundary that still applies. Do not carry forward stale screenshots, element references, window identifiers, or assumptions of semantic completion.

## Step 1: establish the device interaction

Load `walter-computer-use` with `skill_read` before taking any GUI action.

Use its observation and atomic-action loop to establish the current device and application state. Select the smallest relevant app or device reference only after observing the actual target. If the task requires an app-specific reference, load only that reference through the sub-skill's prescribed progressive-knowledge mechanism.

Before handing off, verify that:

- the intended application, window, or device surface is identified from fresh evidence;
- every requested atomic action has a confirmed or freshly inspected result;
- unexpected dialogs, permissions, credentials, recovery screens, or capability limits are reported for the planner to resolve;
- no sensitive or destructive surface was acted on without the required authorization;
- the handoff states what remains to be done and where it must be done.

If the target is absent, ambiguous, permission-blocked, or changed after an action, stop this step and return the live observation. Do not infer success from a running process, an unverified click, or an old capture.

## Step 2: continue with background desktop control

Load `computer-use` with `skill_read` before continuing.

Use the Step 1 handoff to choose the scoped application and capture a fresh state. Re-establish the target from the new capture rather than reusing Walter references. Drive the desktop with the sub-skill's action vocabulary and background-first delivery. After each state-changing action, inspect its structured result and verify the postcondition with a fresh capture or state read.

Between actions, apply these gates:

- a confirmed effect ends that action; do not duplicate it;
- an unverifiable effect requires fresh inspection before any retry;
- a suspected no-op or explicit escalation signal permits the next documented delivery rung only after the fresh inspection;
- stale element references require a new capture and new references;
- browser page content must use the appropriate browser toolset rather than desktop chrome actions;
- foreground input, permission surfaces, secrets, and other sensitive actions remain subject to the sub-skill's safety rules.

Before handing off, record the fresh application/window identity, the final verified state, the actions that are complete, and the exact reason remote control is required. If the task can finish through the local or browser route, finish here and return the verified result. Proceed to Step 3 only when the remaining work depends on a remote interactive Mac session or the user explicitly requires that route.

## Step 3: validate and control the remote Mac

Load `remote-computer-use` with `skill_read` before opening or using the remote route.

Treat the VPS as the client and the interactive Mac as the driver host. Validate the target-side route and live GUI capability before mutation. The remote handoff must identify the intended Mac, user session, application or window, and remaining operation; it must not be used to assume that a VPS-side binary or tunnel proves Mac readiness.

Run the sub-skill's required read-only reachability, health, permission, capture-integrity, and target-window checks. Confirm that the live session is unlocked and that the selected PID/window identity and capture belong to the current target. A transport response, valid image container, or generic success field is insufficient without semantic GUI evidence.

During remote work:

- serialize mutations within the current driver session;
- invalidate element or snapshot references after each new capture;
- verify every mutation with a fresh target-side state read;
- treat unknown or unverifiable completion as a reason to inspect, never as permission to replay automatically;
- keep legacy transport paths as explicit observational or approved fallbacks and never replay an uncertain mutation through a second driver;
- stop before input when the target session, permissions, capture, or window identity is unresolved;
- preserve the no-focus and authorization boundaries established by the earlier steps.

Return the final result with the target Mac identity, verified postcondition, and any remaining blocker. If the remote gate fails, report the precise live failure category—transport, authentication, inactive GUI session, permission, capture integrity, or target resolution—and do not report the GUI task as completed.

## Orchestration contract

The planner remains responsible for the overall user goal and for deciding whether to continue, change route, or stop. Each sub-skill is loaded at its step boundary with `skill_read`; its instructions govern the actions performed in that step. The workflow passes verified observations forward, refreshes state at every boundary, and stops on unresolved safety, identity, permission, or completion evidence rather than guessing.
