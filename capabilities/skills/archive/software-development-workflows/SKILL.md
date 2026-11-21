---
name: software-development-workflows
description: "Use for frontend and software work: build, test, debug."
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [software-development, debugging, testing, review, audit, delivery]
---

# Software Development Workflows

Use this class-level skill for software delivery work that spans discovery, scope, implementation, debugging, testing, review, deployment, or evidence verification. Choose the labeled branch that matches the work instead of loading a one-off workflow. For public-web research, mail, meetings, forms, provider operations, or general Hermes runtime work outside a software delivery path, load `evidence-and-execution-operations`; load both only when a software change and external operation are inseparable.

## Always-on rules

- Inspect the actual repository, runtime, and acceptance criteria before making claims, because summaries and labels are not evidence.
- Keep the requested role boundary explicit: a read-only audit must not edit, and an independent reviewer must not implement the change it is reviewing.
- Make each finding reproducible with a concrete file, line, command, or artifact, because uncited suspicion is not a useful defect report.
- Separate observed facts, hypotheses, and recommendations, because a plausible explanation is not a verified cause.
- Prove a test failure is yours before acting on it: stash the diff and re-run only the suspect files. Suite ordering and shared state produce bulk-run failures that a focused run does not reproduce, so a file that fails in the full suite but passes in isolation is pre-existing and stays out of scope.
- Re-run the named verification in the same environment that matters, because a green claim from another checkout, provider, or harness does not transfer.
- Preserve user changes and isolate experiments, because broad resets or shared workspaces destroy the evidence being evaluated.

## Scope and feasibility

Before building an optional, low-use, cross-boundary feature:

- State the value, expected use, existing manual path, and maintenance cost without inventing usage numbers.
- Count runtime boundaries—surface, transport, gateway, worker, native permissions, reconnect, and cleanup—because file count understates distributed complexity.
- Prefer an existing manual action, then a local change, configuration, or bounded spike before a durable protocol or native integration.
- Set a complexity budget and stop for explicit value confirmation when the design crosses it; technical possibility is not product justification.
- Treat a user cancellation as final: stop related work, revert only this attempt, preserve unrelated files, and do not reopen the decision.

## Feasibility spikes

Use a spike only when working code can answer a decision that documentation cannot.

1. Decompose the idea into two to five observable Given/When/Then questions and order them by risk.
2. Research enough to choose an approach, then build the smallest standalone, disposable artifact.
3. Prefer an interactive CLI, minimal page, server endpoint, or focused test over a log-only demo.
4. Exercise edge cases and competing approaches when relevant; one happy-path run is not validation.
5. End each spike with `VALIDATED`, `PARTIAL`, or `INVALIDATED`, evidence, surprises, and a production recommendation.
6. Do not turn a throwaway spike into production code; start a fresh implementation after the decision.

## Test-first implementation

For new behavior, bug fixes, refactors, and behavior changes, use the RED → GREEN → REFACTOR loop unless the user explicitly approves an exception.

- Write one behavioral test first and run it to confirm the expected failure, because a test that never failed may test existing behavior or the wrong thing.
- Implement the smallest code that passes, then run the focused test and the broader suite before refactoring.
- Refactor only while tests remain green; keep tests behavior-focused, use real code where practical, and cover errors, boundaries, and regressions.
- Work in vertical slices rather than writing a large imagined test pile before implementation.
- Treat an interactive spike, generated code, or configuration as an exception that should be declared, not silently used to bypass test-first work.
- When a deliberate behavior change invalidates a test that pinned the old behavior, rewrite that test in the same change and state the new contract in it. Preserve and strengthen the guardrails it also carried — a test asserting both an allowlist and a security boundary must not lose the boundary check when the allowlist is widened.

## Frontend artifact and browser QA branch

- Establish the audience, job to be done, visual hierarchy, responsive constraints, accessibility needs, and acceptance criteria before styling, because polish cannot repair an undefined artifact.
- Prefer semantic structure, accessible controls, progressive enhancement, coherent tokens, and explicit loading/error/empty/focus/reduced-motion states over isolated effects.
- Treat fonts, media, shaders, third-party assets, and generated content as explicit inputs with fallbacks; preserve factual copy and mark placeholders.
- For canvas, p5.js, games, and interactive sketches, separate setup, state, update/draw, resize, input, export, and cleanup; bound resources and exercise start, interaction, reset, failure, and replay paths.
- For diagrams, choose layout and connector geometry from the target renderer's schema, keep dimensions and wrapping deterministic, and verify the exported scene rather than trusting plausible JSON.
- Confirm the active Tailwind/build configuration before styling, keep reusable components and tokens coherent, and verify production CSS includes the utilities actually used.
- Serve the final artifact from its intended path and verify HTTP/assets, target viewports, keyboard/focus, primary interactions, responsive layout, console/network errors, and important visual states in a real browser.

Read `references/frontend-artifact-qa.md` for the design, canvas, diagram, game, and browser verification checklist.

## Root-cause debugging

For bugs, test failures, build failures, performance problems, and unexpected behavior:

1. Read the complete error and stack, reproduce it, inspect recent changes, and trace the bad value through component boundaries before changing code.
2. Find a working analogue and compare every meaningful difference, including configuration and environment.
3. State one falsifiable hypothesis and test it with the smallest one-variable change.
4. Add a regression test, fix the root cause once, and run focused plus full verification.
5. After three failed fixes, stop patching and question the architecture with the user.
6. When the same tool/error class repeats three times, stop retrying and classify it as transient, rate-limited, configuration, credential, path, or schema failure; diagnose the authoritative source instead.
7. For server unresponsiveness, inspect reboot/uptime, current and previous journals, kernel pressure, all failed and still-restarting services, restart counts, working directories, and executable paths before stopping or masking anything.
8. Select Python debugging by need: `breakpoint()`/pdb locally, direct pytest with `--pdb` for interactive tests, and debugpy or remote-pdb for long-lived or headless processes; remove breakpoints before delivery.

## Codebase inspection and audit

- For a size/composition question, run `pygount` with dependency/build directories excluded and report code, comments, files, and language breakdown separately.
- For a read-only audit, map the tree, establish a no-mutation baseline, capture suite state, trace API/data/UI/test/CI paths, compare documentation with code, and cite every finding.
- For test coverage, map invariants and guard branches to actual test cases instead of relying on a percentage; for provider dispatch, verify each branch's URL, payload, and routing decision.
- Before removing a feature or schema axis, inventory its symbols and fields across production code, tests, docs, generated artifacts, and downstream consumers; preserve unrelated uses, then exercise the public entry point and verify the output contract end-to-end, because a green focused test can leave stale surfaces live.
- For frozen artifacts, verify archive and manifest hashes, run canonical commands in an isolated copy, regenerate claimed artifacts, compare them semantically, and flag by-construction or stale evidence.
- For phased or candidate releases, distinguish deployed/existing, reusable-but-unwired, and missing; verify the actual runtime, permissions, transport, and baseline rather than inferring them from a roadmap.
- For model-facing tools, cross-check schema keys against dispatcher reads, exercise the real entry point, gate mutations, bound pass-through inputs, and fail closed on unknown geometry, backend, or frame state.
- For security assurance, keep credential/catalog/local/control-plane/build/runtime claims separate, redact secrets, test pre-dispatch denial and post-dispatch unknown completion, and never retry a mutation without correlation or idempotency.

## Cleanup and review

- Treat cleanup as distinct from bug hunting: inspect reuse, quality, efficiency, and abstraction depth, search the wider codebase, and apply only evidence-backed changes.
- Use parallel review lanes only when they have decorrelated lenses and the complete diff; deduplicate findings, resolve correctness before micro-optimization, and keep risky public-contract changes for human review.
- For Kanban handoffs, read the durable task record first, map every acceptance criterion to evidence, vary the review lens by round, and choose exactly one outcome: approve, request changes, or escalate.
- A reviewer must not edit the implementation; request targeted changes and independently re-check the next candidate.

## Deployment and rollback gates

- Resolve live and candidate versions from the artifacts themselves and make backup/stage/failed paths unique and unambiguous.
- Run configuration, evidence, and full-test gates before the first production mutation.
- Arm rollback before the first destructive rename, prefer an atomic swap, restore exact bytes on failure, restart the service, and retain the successful backup.
- Do not treat equal version strings as proof of a changed artifact; use functional loading or content identity.
- Reproduce ephemeral evidence immediately before deployment and pin it to the exact candidate revision.

## Completion contract

Report what was actually inspected or executed, what changed, what remains unverified, and any blocker. Never turn a plan, a label, or an invented number into a completed result.

For routing and autonomous-data systems, report completion separately for the catalog/importer, classifier, selection policy, refresh worker, scheduler, and execution integration. Exercise a real refresh before calling a snapshot importer a maintenance agent, and exercise dispatch before calling an advisory selector an active router; these boundaries prevent a tested foundation from being mistaken for the requested end-to-end system. Label classification fixtures explicitly even when their downstream selection uses real benchmark data.
