---
name: research-verification-with-auth-fallback
description: "Use when web research needs verified current prices, exact-date availability, transport details, or comparable AI API tariffs, and a required source may be inaccessible because existing cookies do not establish an authorized session."
type: workflow
requires: [research-evidence-verification, authenticated-session-fallbacks]
---

# Research Verification with Auth Fallback

Run evidence verification first. Invoke the authentication fallback only when a failed session blocks a material claim that cannot be adequately verified from an accessible source. If accessible evidence answers the request, skip the fallback.

## 1. Verify accessible evidence

Load `research-evidence-verification` with `skill_read`. Apply it to the request and preserve the findings already supported by accessible sources.

**Handoff to step 2:** For each claim still blocked by authentication, pass the exact missing field, the constraints it must match, the target service and URL, the observed session failure, the expected account or region if relevant, and any alternative evidence already checked. Pass no secrets or session material.

**Gate:** Confirm that the missing field matters to the answer, that the obstacle is authentication rather than a page or extraction error, and that read-only access to the intended service and account is authorized. If scope or account identity is unclear, ask before proceeding. If access is not authorized, finish with the supported evidence and state the gap.

## 2. Resolve the access blocker

Load `authenticated-session-fallbacks` with `skill_read`. Use it only for the scoped lookup from step 1. Do not expand the search to unrelated accounts or data, bypass a challenge, or perform account-changing actions as part of this workflow.

**Handoff to step 3:** Return the access outcome and, if obtained, only the requested observation, its source and timestamp, and the minimum non-secret context needed to establish that it came from the intended account or an approved alternative source. If blocked, return the blocking stage and the field that remains unknown.

**Gate:** Check that the observation came from the intended source and scope. Keep direct service observations separate from fallback evidence; restored access alone does not verify the claim.

## 3. Reconcile and report

Load `research-evidence-verification` with `skill_read` to resume verification against the original constraints. Merge only evidence that supports the exact claim; preserve the provenance and limits of any fallback source. If access failed or the recovered evidence does not match, leave the claim unverified rather than treating it as a negative result. Report what was verified, what remains unknown, and the next action that would resolve the gap.
