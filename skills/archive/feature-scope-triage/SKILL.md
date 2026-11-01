---
name: feature-scope-triage
description: "Use before low-use or cross-boundary feature builds."
version: 1.0.0
author: W.Alter
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [scope, prioritization, yAGNI, architecture, cost-benefit, cancellation, rollback]
    related_skills: [writing-plans, spike, plan, systematic-debugging]
---

# Feature Scope Triage

## Purpose

Use this skill before implementing an optional feature whose value is uncertain, especially when it crosses machines, processes, transports, platforms, or native dependencies. The goal is not to block useful work; it is to prevent a low-frequency convenience feature from becoming a permanent distributed subsystem.

This skill governs the decision **whether to build**, not the technical implementation after the decision is approved.

## Triggers

Load this skill when any of the following is true:

- The feature is a convenience, experimental, hands-free, cosmetic, or rarely used capability.
- The proposed path crosses a client and a remote backend, or requires a new stream/transport/protocol.
- The implementation touches several layers (UI, transport, gateway, backend worker, native runtime, packaging).
- Native dependencies, microphone/camera access, browser media APIs, WebRTC, persistent daemons, or platform-specific permissions are involved.
- The user signals low expected usage, impatience, or scope rejection: “je ne vais pas tant l’utiliser”, “trop de galère”, “laisse tomber”, “stop”, “pas maintenant”.

## Core rule

**Usage frequency is an architectural constraint.** A feature used once a month does not automatically justify a continuously maintained protocol, a new native dependency, or a cross-machine streaming path. Prefer the smallest existing control path; if the smallest path is still disproportionate to usage, defer or drop the feature.

## Triage procedure

### 1. Establish the value ceiling

Before editing code, state internally or briefly to the user:

- What the feature removes or improves.
- How often it is realistically expected to be used.
- Whether the existing manual path already works.
- What failure would cost in support and maintenance.

Do not invent usage numbers. If the user has already said the feature is rarely useful, treat that as sufficient evidence for a defer/drop recommendation.

### 2. Count the boundaries, not just the files

List the runtime boundaries the feature would introduce or modify:

- UI/client capture or interaction.
- Transport/API or WebSocket messages.
- Gateway dispatch and lifecycle.
- Backend worker/detector.
- Native packages, permissions, or OS-specific packaging.
- Restart, reconnect, buffering, backpressure, and cleanup behavior.

A feature that crosses three or more of these boundaries is not “a small tweak”, even if the code diff looks short.

### 3. Choose the least-footprint path

Evaluate in this order:

1. Existing manual action or existing command.
2. A local-only change at the surface where the feature is used.
3. Configuration or a one-shot script.
4. A throwaway spike, only if feasibility is the real question and the user still values the feature.
5. A durable transport/protocol or native integration, only after explicit value confirmation.

Do not jump from a detected technical limitation directly to a distributed architecture. First ask whether the feature deserves that architecture.

### 4. Set a complexity budget

Before implementation, define a stop line. Examples:

- More than 3 runtime boundaries.
- More than one new protocol/message family.
- New native dependency or OS permission.
- More than 2–3 files for a feature explicitly described as low-use.
- More than a few focused discovery calls before a concrete minimal patch exists.

Crossing the stop line requires a value checkpoint, not silent continuation. Present the trade-off plainly: keep the manual path, run a bounded spike, or approve the durable build. Do not continue by momentum.

### 5. Respect a cancellation immediately

If the user rejects the scope or says the feature is not worth the hassle:

1. Stop designing and stop making new calls related to that feature.
2. Cancel the active implementation/test TODOs.
3. Revert only changes made by the current attempt.
4. Preserve pre-existing modifications and untracked files.
5. Verify the targeted diff is clean; do not run a broad test suite for a canceled feature unless cleanup itself needs verification.
6. Report in one or two sentences what was stopped and what was preserved.

Do not propose a second architecture, do not salvage partial code into a different feature, and do not re-open the decision in the closing message.

## Cost-benefit framing

Use a compact table when the decision is not obvious:

| Option | User value | New maintenance surface | Recommendation |
|---|---:|---:|---|
| Keep existing manual path | Usually enough | None | Default for low-use features |
| Bounded spike | Answers feasibility | Temporary | Only when the answer changes a real decision |
| Durable cross-boundary build | Highest convenience | Protocol, lifecycle, support, platform risk | Only with explicit value |

The recommendation should be based on total maintenance surface, not on whether the proposed code is technically elegant.

## Implementation handoff

Only after the user accepts the complexity budget:

- Load the implementation skill that matches the subsystem.
- Write a small plan with explicit files and verification.
- Prefer a spike when an unknown could invalidate the architecture.
- Keep the first production patch reversible and bounded.

If the user does not explicitly approve the durable path, default to the manual path or defer. “Technically possible” is not the same as “worth maintaining”.

## Verification after cancellation

Use a targeted check, not broad cleanup:

- Inspect `git status --short` and the targeted `git diff`.
- Confirm files created by the canceled attempt are absent or intentionally retained only if the user requested that.
- Confirm unrelated modified/untracked files are unchanged.
- Never reset the whole repository, stash blindly, or delete user files to make the tree look clean.

## Reference

See `references/remote-feature-stop-example.md` for the concrete Mac-client/remote-VM wake-word case that motivated this workflow.

## Related skills and overlap

This skill complements rather than replaces:

- `writing-plans` for an approved implementation plan.
- `spike` for a bounded feasibility experiment that still has decision value.
- `systematic-debugging` for diagnosing an existing failure.
- `plan` for plan-only work.

If these skills accumulate overlapping scope gates, consolidate the rules into this umbrella during curator maintenance rather than creating narrower one-off skills.
