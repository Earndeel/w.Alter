# Software delivery depth

Use this reference after the repository, runtime, scope, approval boundary, and verification command are fixed.

## Intake and feasibility

- State the value, expected use, existing manual path, and maintenance cost before building an optional cross-boundary feature; do not invent usage numbers.
- Count surface, transport, gateway, worker, native-permission, reconnect, and cleanup boundaries because file count understates distributed complexity.
- Prefer an existing manual action, then a local change, configuration, or bounded spike before a durable protocol or native integration. Set a complexity budget and stop for explicit value confirmation when it is exceeded.
- Turn a spike into two to five observable Given/When/Then questions ordered by risk. Build the smallest disposable artifact, exercise edge cases and competing approaches, and finish with `VALIDATED`, `PARTIAL`, or `INVALIDATED`, evidence, surprises, and a production recommendation.
- Treat cancellation as final: stop related work, revert only the current attempt, preserve unrelated files, and do not reopen the decision.

## Test-first implementation

- For new behavior, bug fixes, refactors, and behavior changes, write one behavioral test and run it to prove the expected failure before implementing.
- Make the smallest change that passes, then run the focused test and the broader repository checks before refactoring. Refactor only while green, keep tests behavior-focused, and cover errors, boundaries, and regressions.
- Work in vertical slices rather than writing a large imagined test pile. Declare interactive spikes, generated code, and configuration exceptions instead of silently bypassing test-first work.
- When a deliberate behavior change invalidates an old test, rewrite it with the new contract in the same change and preserve every unrelated guardrail it carried.
- Prove a bulk-suite failure is caused by the current change: isolate the suspect files and re-run them. A failure that disappears in isolation is pre-existing and remains out of scope.

## Root-cause debugging and service recovery

1. Read the complete error and stack, reproduce it, inspect recent changes, and trace the bad value through component boundaries before editing.
2. Find a working analogue and compare meaningful code, configuration, and environment differences.
3. State one falsifiable hypothesis and test it with the smallest one-variable change.
4. Add a regression test, fix the root cause once, and run focused plus full verification.
5. After three failed fixes, question the architecture with the user. After three occurrences of the same tool or error class, stop retrying and classify it as transient, rate-limited, configuration, credential, path, permission, or schema failure; inspect the authoritative source instead.
6. For an unresponsive host or service, gather uptime and reboot, current and previous journals, kernel pressure, failed and still-restarting units, restart counts and policy, working directories, and executable paths before stopping anything. Stop only identified offenders, then re-check active state, restart counts, memory pressure, reachability, and the intended service path.

Choose `pdb` for a short local frame, direct pytest with `--pdb` for an interactive failing test, and `debugpy` or `remote-pdb` for a long-lived or headless process. Bind listeners to loopback and remove breakpoints, listeners, and temporary credentials before delivery.

## Cleanup and independent review

Run cleanup after correctness works, not instead of it. Read the complete diff and search the wider codebase through decorrelated lenses: reuse, quality, efficiency, and altitude. Require a concrete file or line, cost, confidence, and risk for every finding; apply safe changes first and route risky public-contract or concurrency changes to human review.

For an independent handoff, read the durable task record and original acceptance criteria, map each criterion to implementation and execution evidence, inspect the actual artifact, and choose exactly one outcome: approve, request targeted changes, or escalate an external prerequisite. The reviewer must not edit the implementation.

## Deployment and rollback

Resolve live and candidate versions from the artifacts themselves, make backup/stage/failed paths unique, and run configuration, evidence, and full-test gates before the first production mutation. Arm rollback before destructive renames, prefer an atomic swap, restore exact bytes on failure, restart the owning service, retain the successful backup, and verify functional loading rather than trusting equal version strings. Reproduce ephemeral evidence immediately before deployment and pin it to the exact candidate revision.

## External coding agents

Before invoking Claude Code, Codex, OpenCode, or another coding CLI, freeze repository status, branch or worktree, working directory, tool availability, auth mode, task scope, allowed paths, test command, stop condition, and spend or turn limits. Prefer bounded one-shot commands; use an isolated worktree and a PTY-backed session only when interaction requires it. Treat trust prompts, permissions, sandbox fallbacks, OAuth, API keys, service PATH, provider protocol, endpoint path, model ID, and auth headers as separate readiness gates.

Use Claude Code print mode, Codex `exec`, and OpenCode `run` for bounded work. For Codex, run inside a Git repository and use the narrowest sandbox that matches the write scope; if workspace sandboxing cannot initialize, use an explicitly isolated worktree and tightly prompt any broader access. For OpenCode, check the resolved binary and auth actor when shells differ, and end interactive sessions with Ctrl+C or process termination. A protocol mismatch, duplicated `/v1`, or conflicting auth headers is a transport diagnosis, not a reason to rotate credentials blindly.

Keep each worker in one repository or worktree, inspect the complete diff and worker output independently, run focused and repository-required checks, preserve unrelated changes, and never commit, push, merge, or post a PR solely because a worker reported success.

## Conversational intake gates

Model guided intake as a state machine with explicit readiness, approval, revision, and completion states. Parse each tool result once and isolate per-call failures. Preserve source IDs, timestamps, confidence, contradictions, and unresolved questions in the internal snapshot; do not advance while a required gate is pending or marked `revise`. Hand off only a durable snapshot with validated required fields, while keeping client-facing style separate from internal routing state.

## Routing and autonomous-data systems

Report completion separately for the catalog or importer, classifier, selection policy, refresh worker, scheduler, and execution integration. Exercise a real refresh before calling a snapshot importer a maintenance agent, and exercise dispatch before calling an advisory selector an active router. Label classification fixtures explicitly even when downstream selection uses real benchmark data.
