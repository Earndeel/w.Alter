---
name: web-research-evidence-chain
description: "Use when public web research needs verified current prices, exact-date availability, transport details, or comparable AI API tariffs, and a material evidence gap may require authorized read-only access after an existing session fails."
type: workflow
requires: [universal-web-extraction-router, research-evidence-verification, authenticated-session-fallbacks]
---

# Web Research Evidence Chain

Run public discovery and extraction first, then verify the evidence. Use authenticated fallback only if verification identifies a material question that an authorized account source can answer and the existing session does not provide access. Skip fallback when public evidence is sufficient. For extraction-only requests, use the router directly.

## 1. Gather public evidence

Load `universal-web-extraction-router` with `skill_read`. Give it the research objective, known URLs or search scope, required fields, and any constraints that affect extraction.

**Check:** Make sure the extracted content describes the requested item or claim and actually contains the required fields. Separate usable observations from leads, extraction errors, and access blocks. A failed read is not evidence that an item is absent.

**Hand off to step 2:** The original constraints, extracted observations with source URLs and retrieval times, and a list of unresolved fields with the reason each is missing.

## 2. Verify claims and decide whether to escalate

Load `research-evidence-verification` with `skill_read`. Check each material claim against the original constraints and the observed source state. Record what the evidence supports, preserve conflicting observations, and compare prices only where the billing basis is compatible.

**Check:** If a gap comes from poor extraction or the wrong page state, send a targeted public follow-up to step 1. If public evidence is sufficient, finish. Proceed to step 3 only if a remaining gap matters to the answer, an authorized account source is likely to resolve it, and the existing cookie-backed or persistent session has failed to reach the required view. If authorization or account identity is unclear, ask rather than guessing.

**Hand off to step 3:** The exact unresolved claim or field, why public evidence could not resolve it, the service and intended account, the observed session failure, and the permitted read-only scope. Do not pass secrets.

## 3. Resolve only the authorized gap

Load `authenticated-session-fallbacks` with `skill_read`. Use it to validate the intended account and try approved read-only sources. Retrieve only evidence needed for the outstanding claim. Stop at ambiguous account selection, an authentication challenge requiring user action, or any step that would change account state or grant new access. Never include credentials, cookies, tokens, or verification codes in a handoff or report.

**Check and hand back:** Distinguish evidence observed in the intended service from evidence found in an approved alternate source. Return the minimum relevant observation with its source, timestamp, and non-secret account context, or return the blocker and the field still unresolved. Access failure does not establish that data is absent.

## Close out

Load `research-evidence-verification` again with `skill_read` after any authenticated fallback and reassess the new observation against the same constraints. Report the verdict, supporting sources and dates, and any consequential uncertainty. Keep verified findings separate from leads and blocked checks; do not upgrade a claim merely because a source was authenticated.
