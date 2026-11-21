---
name: computer-use-operations
description: Use when operating or extending Computer Use safely.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [computer-use, cua-driver, accessibility, remote-desktop, benchmarking, plugins]
    related_skills: [computer-use, systematic-debugging]
---

# Computer Use Operations

Class-level workflow for safe Computer Use operation, driver wiring, capture/AX resilience, remote Mac control, state restoration, benchmarking, and update-safe extension. The bundled `computer-use` skill owns the action vocabulary; this umbrella owns the contracts around it.

## When to Use

- A Computer Use action must be observed, verified, retried, or benchmarked.
- CuaDriver/AX capture, target identity, permissions, session state, or window selection is unreliable.
- Hermes runs on a VPS while the permission-owning GUI is a remote Mac.
- A plugin, wrapper, backend factory, or model-routing change must survive updates.
- A layout/state restoration or an action-result completion claim needs proof.

## Safety Contract

- Treat TCC/permission state, capture integrity, AX target validity, action delivery, UI readback, and task postcondition as separate verdicts.
- Bind every element token/index and pixel coordinate to the newest `(session, snapshot, pid, window_id, geometry, coordinate basis)`; invalidate it after every capture or mutation.
- `ok`, `confirmed`, `effect=unverifiable`, a non-empty image, a valid PNG, or a running process proves transport/progress only; never call the task complete without fresh state evidence.
- Use AX/semantic actions before pixels, deterministic APIs/files before GUI, and vision only for unresolved visual ambiguity. Never compensate for invalid pixels with a stronger model or blind retries.
- Do not drive passwords, OTPs, payment, permissions, recovery, or destructive controls without the applicable approval gate. An unknown completion after input is not a no-op; never replay automatically.
- Keep the user's app/session open unless explicitly asked otherwise. End disposable driver sessions and remove only artifacts created by the task.

## Fresh-Observation Ladder

1. Capture the exact window state with current AX elements, snapshot ID, and optional screenshot diagnostics.
2. Choose one target from that snapshot and execute one bounded action.
3. Capture the same target again and compare the requested semantic/visual postcondition.
4. If delivery is `unverifiable`, perform at most one targeted AX readback for an observable state change; unchanged state returns adaptation/failure, not an automatic second click.
5. If pixels are required, require explicit frame validity, substantive coverage, and target identity before vision or coordinate actions.
6. Clean up and verify the session ended without altering unrelated user state.

For layout restoration, success requires both a fresh screenshot matching the target geometry and a fresh AX snapshot showing the expected anchors/visibility, with overlays/modals absent. Use an official Reset/Default path instead of replaying an unknown toggle history.

## Driver and Backend Architecture

Keep Hermes core responsible for the public `computer_use` schema, approvals, session lifecycle, backend lifecycle, and multimodal result shaping. Put custom capture policy, target selection, strategy registries, and compatibility checks behind a narrow backend factory/plugin boundary outside the checkout where possible.

Resolve the driver through the documented command contract; if a manifest supplies empty command plus args, retain the already-resolved wrapper and use those args rather than executing a remote machine's absolute path. Embedded daemon/permission modes are contracts, not inherently local-only: a remote shim may forward only a bounded, validated invocation to the enrolled GUI host. Reject unknown or duplicate flags and unsafe socket paths before transport.

Fail closed when the host seam or plugin contract is missing. Never silently fall back to the built-in backend while claiming the custom policy is active, coerce an explicit unrestricted mode to standard, duplicate the approval layer, or add a second model-facing GUI tool when the existing front door can express the capability.

Use canonical `config.yaml` for backend/strategy/model routing. Keep capture strategy independent from auxiliary vision model selection. Test both ordinary and unrestricted/embedded paths, manifest discovery, plugin precedence, approval propagation, and the actual model-facing schema.

## Capture, AX, and Window Resilience

Normalize direct and structured driver response envelopes through one adapter. Preserve explicit `elements=[]`, `tree_markdown`, `screenshot_frame_valid`, `screenshot_error`, and coverage fields; do not turn an empty structured tree into a fake actionable `AXWindow`.

Select windows by app identity, exact PID/window ID, on-screen status, and substantive geometry rather than z-index alone. Helper/title-bar strips can sit above the real surface. Preserve explicit target pins; if all candidates are off-screen/invalid, return no target and clear stale targeting.

Permission granted is not capture proof. A nullable direct capability field means “not checked.” Use non-prompting diagnostics first, avoid consent-producing probes in unattended work, and keep AX-only evidence separate from pixel validity. If AX is coherent but pixels are invalid, semantic diagnostics may continue but visual claims and vision calls must stop.

Use current element tokens or snapshot-bound indices. A fresh token alone is not UI change; compare a generic semantic fingerprint of role, label, value/state, and meaningful bounds while excluding tokens, generation IDs, and traversal order. Keep `action_reached_driver` separate from `result_verified`, and make safety aggregates explicit when required fields must remain false (for example, no blind coordinate click, zero screenshots, zero vision calls).

## Remote Mac Operations

A VPS-side process cannot inherit the Mac user's Accessibility or Screen Recording grants. The topology is VPS Hermes → authenticated SSH/Tailscale tunnel → Mac loopback CuaDriver endpoint → permission-owning signed app/daemon → AX/ScreenCaptureKit/input.

Before any mutation, verify the target Mac's interactive GUI session, signed driver identity, TCC state, window list, screenshot dimensions/format/content, and a harmless AX read. An HTTP 200, valid PNG, or running process is not semantic success. Keep the legacy pixel server as an explicit observational/temporary fallback, never an automatic replay path.

Use loopback-only endpoints, long-lived stdio/MCP forwarding where required, bounded bearer auth, and exact session IDs. Preserve frontmost/focus contracts and stop when the target is locked, asleep, unresolved, or outside the user's named browser/app scope. Never foreground or click TCC dialogs silently.

Prefer direct AX/element actions; use pixels only from the same fresh capture and its coordinate metadata. Never hard-code Retina `/2`; return physical/logical dimensions and scale factors or fail closed. A remote action that times out after dispatch is unknown completion, not permission to repeat.

## Update-Safe Extension

Keep policy code outside the Hermes checkout where possible. Use the smallest existing seam: backend variation, factory registry, named plugin backend, then strategy registry. Add a compatibility checker and a focused recovery patch for any unavoidable core edit. Preserve user work, test patch applicability against a clean worktree, and verify plugin discovery/config resolution after updates.

Do not delete or reset state databases because they are untracked or surprising; resolve the active Hermes home and exact runtime path first. Cleanup only identified disposable caches. Run the repository's canonical test wrapper, focused contract tests, config validation, lint/diff checks, and at least one real target-host smoke path after the final change.

## Benchmarking

Freeze model IDs/routes, screenshot fixture, prompt/output format, provider/config flags, warm/cold condition, and target task. Measure end-to-end Hermes wall time, not provider generation time. Run enough independent samples to show raw values plus median/mean/min/max and tail spikes; do not present small-sample p95 as precise.

Separate visual perception, perception latency, action reliability, verification latency, and false-success rate. Use disposable non-destructive fixtures. A screenshot-only benchmark is not a Computer Use benchmark; a faster invalid/black capture is not a better model. Route fast vision through a confidence/timeout gate to a tested reasoning fallback, then verify the action with a fresh capture.

## Evidence and Completion

For every action/task, retain structured evidence for target identity, pre-state, action delivery, post-state, approvals, retries/escalations, and cleanup. A terminal `needs_user_input`, definitive success, or impossible result is a user-facing completion boundary only when the producer certifies safe final text; otherwise stop further tool dispatch and use the generic text-only continuation contract. Never expose raw stack traces, transport IDs, credentials, or internal diagnostics as final text.

## Verification Checklist

- [ ] Exact target window/app, session, snapshot, and current refs are bound.
- [ ] TCC/AX/capture verdicts are separated and pixels are valid before vision/input.
- [ ] Action result was read back with fresh state; unknown completion was not replayed.
- [ ] Layout/state restoration has screenshot and AX evidence and no overlay remains.
- [ ] Remote Mac target and permission-owning process were verified, not just VPS plumbing.
- [ ] Custom driver/plugin contracts fail closed and survive an update path.
- [ ] Benchmark reports raw latency/reliability evidence without conflating perception with action.
- [ ] Sensitive actions, temporary sessions, focus, and artifacts were safely handled.

## References

- `references/absorbed-source-routing.md` — mandatory original-package routing when condensed rules lack operational detail.

- `references/computer-use-operations.md` — condensed driver, remote-host, restoration, and benchmark decision tables.
