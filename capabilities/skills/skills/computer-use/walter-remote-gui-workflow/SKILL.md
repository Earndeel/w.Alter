---
name: walter-remote-gui-workflow
description: Use when Monsieur needs W.Alter on a VPS to inspect or manipulate a remote Mac GUI through Walter Operator with verified desktop actions.
type: workflow
requires: [walter-computer-use, computer-use, remote-computer-use]
---

# Remote GUI orchestration

Apply this chain when the requested outcome requires interaction with a remote Mac desktop. If a suitable CLI/API/file or browser-content route exists, route there instead. This workflow coordinates the three skills; their procedures remain authoritative in their own files.

## 1. Establish the Operator task

load walter-computer-use with skill_read.

Use its planning boundary to translate Monsieur's request into a scoped observation and the next atomic action. Load only references relevant to the actual app or surface.

Hand to step 2: the authorized goal, intended device/app/window, next observation or action, observable postcondition, and any unresolved target or permission questions.

Check before continuing: the task requires a device surface, the target is grounded in observed facts or explicitly marked unresolved, and the proposed action stays within Monsieur's scope. Hermes retains planning and completion decisions.

## 2. Prepare the desktop interaction

load computer-use with skill_read.

Use its current action vocabulary, capture strategy, and verification/escalation rules to prepare the scoped interaction. This stage prepares execution; do not send remote input before step 3 passes.

Hand to step 3: the capture/action plan, required capabilities, intended app/window, postcondition, and applicable approval constraints. Treat existing observations as provisional until remote freshness and identity are checked.

Check before continuing: the plan uses the supported wrapper contract, defaults to background delivery, and specifies how an uncertain effect will be inspected before any retry. Resolve browser page-content work through its separate toolset.

## 3. Validate the remote host and execute

load remote-computer-use with skill_read.

Apply its target-host, transport, session, permission, and capture-integrity gates before mutation. Confirm that execution reaches the intended Mac rather than the VPS desktop. Use its documented fallback only when applicable and carry forward the same goal, target, and approval constraints.

Hand back to the Operator loop: current remote session and target identity, fresh scoped state and reference validity, capability/gate results, action verdict, completion certainty, and evidence for the requested postcondition.

Check before execution: all gates required for this action pass and the current target is unambiguous. If a gate fails, return its precise blocker to Hermes; do not work around it by changing drivers or input modes.

## Continue and finish

For each action, apply step 2's interaction contract through step 3's validated remote route, then return compact facts to step 1 for Hermes to choose the next action. Reuse loaded skills; refresh live evidence whenever state or target validity changes.

Between actions, compare the verified result with the postcondition. Invalidate superseded references. Route unexpected dialogs, changed scope, permission requirements, and uncertain completion back to Hermes before further input. Never replay an uncertain mutation through another driver; follow the loaded skills' verification and escalation gates.

Finish only when Hermes can connect fresh evidence to Monsieur's requested outcome. Report the verified result or precise remaining blocker, and perform the remote skill's session/test-artifact cleanup without disturbing persistent services.
