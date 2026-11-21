---
name: scrapling-to-playwright-cdp
description: "Use when a Scrapling bulk-fetch, crawl, MCP setup, block investigation, or diagnostic task leads to browser interaction that requires Playwright over CDP because native browser tools fail or a persistent Chromium session is needed."
type: workflow
requires: [scrapling, playwright-cdp-browser-control]
---

# Scrapling → Playwright CDP

## Scope

Orchestrate extraction or diagnosis first, then targeted browser interaction. Delegate implementation details to the sub-skills; do not reproduce their installation, fetching, browser setup, or interaction procedures.

This chain is not the default for a single known-URL extraction, nor a reason to launch a browser after a successful crawl. Use the second stage only when its entry checks pass.

## 1. Extract or diagnose with Scrapling

**load scrapling with skill_read** before performing this stage.

- Establish the URL set or crawl scope, requested fields, output destination, and completion criteria.
- Follow the loaded skill for the relevant bulk operation, crawl, MCP configuration, block investigation, or backend diagnostic.
- Keep successful results separate from failed or incomplete targets. Record enough evidence to distinguish setup failures, access blocks, missing content, and genuine interaction requirements.

**Handoff packet:** target and final URLs; requested fields or browser outcome; validated results and artifact locations; unresolved targets; observed errors or block evidence; attempts already made; and any known session requirements. Include session identifiers or profile references only when relevant, never secret values.

### Gate before browser escalation

- Validate content and required fields, not merely HTTP success; reject challenge pages and empty or unrelated results as successful extraction.
- If the task is complete, return results and stop.
- If the issue is only installation, MCP availability, or fetch configuration, resolve it within the Scrapling stage or report the blocker; do not treat CDP as a generic setup fix.
- Proceed only when unresolved work needs browser interaction and native browser tools have failed or are unavailable, **or** a persistent Chromium session is required. Record which condition applies. If persistence is not required and native tools are available but untried, try them before escalating.
- Preserve the Scrapling → Playwright CDP order for this workflow. The second skill's fetch-only fallback is not an instruction to restart this chain or create an automatic retry loop.

## 2. Resolve the browser-dependent remainder

**load playwright-cdp-browser-control with skill_read** before performing this stage.

- Consume the handoff packet and limit browser work to unresolved targets or required interactions.
- Follow the loaded skill to verify the CDP endpoint and connect to the appropriate existing Chromium context/profile.
- Check the selected page, domain, and authentication state before acting. Do not assume a Scrapling session is shared with the CDP browser or that cookies transfer automatically.
- Preserve shared sessions and unrelated tabs; never clear all cookies or replace a persistent profile to solve a target-specific problem.
- Perform only the interactions needed for the stated outcome, within the user's authorization. Pause for user input when authentication, consent, or a challenge cannot be completed appropriately.

**Handoff to completion:** final URLs, verified browser outcomes, recovered records or artifact locations, unresolved blockers, and a non-secret session reference if future continuation requires it.

### Completion checks

- Confirm the intended page state or operation outcome using page evidence, not merely a successful click or navigation call.
- Validate recovered data against the original fields and scope. Merge with earlier results by a stable URL or record key, retaining provenance and avoiding duplicates.
- Report complete, partial, or blocked status explicitly. Distinguish verified extraction from observed browser state and unverified assumptions.
- Release task-owned temporary resources without closing shared browsers or destroying persistent sessions. Record remaining work rather than cycling automatically between the two skills.
