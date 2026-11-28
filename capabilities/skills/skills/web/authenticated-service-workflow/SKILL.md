---
name: authenticated-service-workflow
description: "Use when Monsieur asks to open, inspect, or manage one of his web accounts and the authorized browser session may require a human handoff or Bitwarden support."
type: workflow
requires: [web-service-browser, human-in-the-loop-gate, bitwarden-integration]
---

# Authenticated Service Workflow

Run the steps in order, skipping unneeded branches. If the existing session is valid and the task has no sensitive step, finish in step 1. A sign-in prompt alone does not justify vault maintenance. Standalone vault work belongs to `bitwarden-integration`, not this workflow.

## 1. Open the service and check the account

Load `web-service-browser` with `skill_read`. Use the supported managed browser session for Monsieur's authorized account. Verify the service origin, the visible account when available, and the requested action before proceeding. Do not extract cookies or other session credentials, or fall back to historical extraction instructions.

If the account is verified and no sensitive step is needed, complete the requested work and go to Closeout. If a sensitive control blocks progress, stop before interacting with it. Hand step 2 the browser tab reference, verified origin, expected account, requested action, and a non-secret description of the blocker. If the origin is unexpected or the account is wrong, stop rather than attempting authentication there.

## 2. Hand the sensitive step to Monsieur

Load `human-in-the-loop-gate` with `skill_read`. Present the exact step Monsieur must complete directly in the browser. Do not ask him to send secrets in chat. On cancellation, stop. On timeout or ambiguous state, do not resume without a fresh gate. After Monsieur confirms completion, inspect a fresh browser state that does not capture secrets. Recheck the origin, account, and next control; do not reuse old element references or treat confirmation as proof of success.

If the blocker is cleared, resume step 1 in the verified tab and skip step 3. If a specific Bitwarden dependency remains, hand step 3 the tab reference, verified origin, expected account, non-secret blocker, and exact scope Monsieur authorized. Permission to resume browsing is not permission to use or maintain the vault.

## 3. Resolve the Bitwarden dependency only if needed

Load `bitwarden-integration` with `skill_read`. For browser sign-in, use only sealed native autofill explicitly approved for this exact account and origin. Verify the item match using non-secret metadata; if the match is ambiguous, ask Monsieur to choose. Never retrieve a raw credential through the CLI for browser use. Send vault unlocks and other human-only challenges back to step 2.

If there is a confirmed vault issue, take only the authorized maintenance action. Verify the vault account and server before acting, and verify backup readiness before any disruptive recovery. Return only a non-secret status: resolved, still blocked, or needs Monsieur. Do not pass passwords, codes, tokens, cookies, or vault contents between steps. If resolved, return to step 1 for a fresh browser check; if a sensitive control remains, return to step 2. If no authorized path remains, report the blocker without attempting a workaround.

## Closeout

Verify the requested result using first-party page evidence, such as the intended dashboard or the resulting plan status. If it cannot be verified, report it as unconfirmed. Close workflow-owned tabs on completion or cancellation; keep a tab open only while an active human handoff needs it. Report the outcome or blocker without secrets.
