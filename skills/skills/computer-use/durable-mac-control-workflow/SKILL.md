---
name: durable-mac-control-workflow
description: "Use when designing or verifying update-safe Hermes Computer Use that must then operate Monsieur's Mac through the SSH screen server and validate or recover its remote connection."
type: workflow
requires: [durable-computer-use-architecture, mac-computer-use-ssh, ssh-mac-remote-control]
---

# Durable Mac Control Workflow

Use this chain when a task spans the Hermes extension boundary, live Mac screen control, and SSH transport verification or recovery. For tasks confined to one of these concerns, use its sub-skill directly.

Follow the order below. Loading and planning precede desktop actions; a missing connection discovered in step 2 becomes a handoff to step 3, not a reason to attempt blind input. The sub-skills own implementation details, commands, and operating safeguards.

## 1. Establish the software contract

load durable-computer-use-architecture with skill_read.

Determine the applicable backend, strategy, vision route, and compatibility boundary. Perform the architecture work or verification required by the task without expanding it into an unrelated redesign.

**Handoff to step 2:** the selected control path, configuration and compatibility evidence, intended Mac target, and remaining live-validation questions.

**Gate:** distinguish software verification from desktop verification. Stop on an incompatible host contract or unresolved backend selection; do not silently substitute another backend. A software pass permits live inspection but does not establish that capture or input works.

## 2. Establish the desktop control plan

load mac-computer-use-ssh with skill_read.

Use the handoff to determine whether visible GUI control is needed. Inspect passive health, control status, and a fresh screenshot when reachable. Establish the exact application or browser target, coordinate mapping, task approval requirements, and observable success condition using this sub-skill.

**Handoff to step 3:** the required screen-server connection, observed health and capture results, target identity, pending actions, and any transport failure. Keep approval tokens private. If unreachable, hand off the failed check rather than attempting input.

**Gate:** an unusable image, unknown target, or unresolved input permission blocks visible actions. Classify the blocker as transport, capture/TCC, targeting, or approval so the next step addresses the correct layer.

## 3. Validate or recover remote access, then complete live verification

load ssh-mac-remote-control with skill_read.

Validate the actual remote host and connection against current instance instructions and live evidence. Repair only the SSH, tunnel, or session issue required by the handoff; use reconnection and cmux procedures only when relevant. A healthy connection needs verification, not reconfiguration.

**Return handoff to step 2:** verified Mac identity, working connection and screen-server reachability, recovery evidence, and any remaining desktop blocker. Transport recovery does not resolve TCC or grant control approval.

**Gate before resuming:** repeat step 2's passive checks after recovery. Refresh the screenshot, target identity, coordinate mapping, and approval status; do not reuse stale action assumptions. Resolve conflicting legacy examples through current instance instructions and live measurements.

Resume the pending desktop task under mac-computer-use-ssh. Verify each consequential action against its expected visible effect and release control when finished. If compatibility changed during recovery, return to step 1 before further input.

## Completion and stopping

Finish only when the requested software checks and live outcome have supporting evidence and control has been released. Report software compatibility, transport health, and observed desktop effect separately. If a gate remains blocked, stop dependent actions and identify the failed check and required intervention; connection success or an accepted input request alone is not task completion.
