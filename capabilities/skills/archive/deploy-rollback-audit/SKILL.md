---
name: deploy-rollback-audit
description: Review a deploy/rollback script for rollback safety.
version: 1.0.0
author: Hermes Curator
license: Proprietary
metadata:
  hermes:
    tags: [deploy, rollback, review, release, audit]
    related_skills: [evidence-integrity-verification]
---

# Deploy / Rollback Script Audit

## When to Use

Use when asked to independently review, gate, or vet a **transactional deployment script** — one
that backs up a live artifact, stages a candidate, swaps it into place, verifies, and can roll
back on failure (e.g. a plugin/package/versioned-tree deploy with `set -euo pipefail` + a
`trap ... rollback`). The reviewer's bar: a failure at *any* point must return the system to the
pre-deploy state (or leave it demonstrably restorable), and every gate must be real, not nominal.

## The audit checklist

1. **Resolve the dynamic baseline, don't trust the summary.** Read the *currently live* version and
   the *candidate* version from their version files yourself (`version_of()` reads
   `<dir>/plugin.yaml`). Confirm the BACKUP/STAGE/FAILED paths embed the live version plus a unique
   timestamp so a rollback dir is unambiguous and restorable. Ask: does the printed
   `rollback_version` actually differ from the deployed version?
2. **Gates must run fail-closed and BEFORE any production mutation.** Config assertions
   (plugin enabled, backend wired), an evidence gate (`passed==true`, expected counts), and the
   full test suite must all execute prior to the first `mv`/`cp` against the live path. A gate that
   runs after the swap is too late.
3. **Arm the rollback BEFORE the first destructive step.** The classic bug: a `swapped=1` flag (or
   the code that decides whether the trap should restore) is set only *after* both
   `mv "$LIVE" "$FAILED"` and `mv "$STAGE" "$LIVE"` complete. A failure/interrupt landing in that
   window leaves production WITHOUT the artifact and the trap refuses to restore. Set the arm flag
   (or drop a marker file) immediately before the first move so every post-mutation failure
   triggers the restore. Prefer an atomic rename-based swap where possible.
4. **Verify the swap functionally, not just by version string.** A version-equality check is
   **vacuous when the live and candidate share a version** (both `1.3.0`): it passes even if the
   swap was empty. Always instantiate the artifact / backend / service in a side-effect-free way
   and assert it loads (proxy construction), assert the real registered surface, and grep the
   actual service-health line — verify the probe string against real CLI output (e.g.
   `hermes gateway status` shows `✓ User gateway service is running`) rather than guessing the
   format.
5. **Rollback path must restore exact bytes and restart the service.** Confirm the rollback copies
   the BACKUP dir back (not a re-run of the candidate), cleans transient rollout dirs, and restarts
   the gateway/service so the restored artifact is actually in use — and logs its own output to a
   file so a broken rollback is diagnosable.
6. **Success path keeps the backup and clears transient artifacts.** The winner keeps the backup dir
   around for a manual revert and removes only the failed/transient dirs before clearing the trap.

## Pitfalls

- **Version collision ⇒ dead version gate.** When live and candidate versions are equal, any
  `version == candidate` check proves nothing about content. Rely on a functional load/instantiation
  gate; suggest a version bump or a build/source hash so `rollback_version` is distinguishable.
- **`swapped` style flags set too late** are the #1 rollback hole. Arm-before-mutate, always.
- **PATH-dependent bare command names** (`hermes gateway restart`) make the deploy succeed or fail
  based on the caller's PATH; prefer an absolute/resolved path or assert it.
- **Trusting a pre-recorded "N passed" suite** — re-run the full suite in the deploy's exact
  `PYTHONPATH`/venv; a green closure is only true if you reproduced it (see
  `evidence-integrity-verification`).
- **Ephemeral E2E evidence** (an `e2e.json` gate) must be regenerated immediately before the deploy
  reads it, and pinned to the exact generator+candidate revision; a stale/flaky evidence file can
  silently gate a release on an older run (see `evidence-integrity-verification` §7).