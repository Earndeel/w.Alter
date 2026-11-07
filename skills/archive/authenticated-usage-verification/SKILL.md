---
name: authenticated-usage-verification
description: "Use when checking live authenticated usage or quotas."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [browser, authentication, usage, quota, credits, cost, verification, read-only]
    related_skills: [authenticated-session-fallbacks, webtop-authenticated-browsing, camoufox-max-api-current]
---

# Authenticated Usage Verification

Use this class-level skill when Monsieur asks to inspect a live usage counter, quota, plan limit, credit balance, reset window, or marginal cost in an authenticated web service. The goal is evidence-backed measurement, not a plausible number derived from memory or from an unrelated public pricing page.

## When to Use

Use for live, authenticated quota/usage checks and for a deliberately authorized control run whose before/after impact must be verified. Do not use it to infer current state from old session notes or public pricing alone.

## Core rules

- Read the live first-party usage surface. Hindsight, cached notes, and a successful cookie count are not current account state.
- Keep the operation read-only unless Monsieur explicitly authorizes a controlled consuming run.
- Treat displayed **credits**, rolling limits, weekly limits, purchased balances, and reset actions as separate metrics until the UI explicitly connects them.
- Never claim that a run cost zero merely because one displayed counter did not move. Report exactly which visible metric was unchanged.
- Never log or return passwords, MFA codes, cookies, bearer/session tokens, localStorage secrets, authorization headers, encrypted blobs, or signed URLs.
- Use a temporary authenticated browser context and delete it after the check.

## Workflow

### 1. Establish scope and a live baseline

1. Identify the exact service, account, product surface, model/mode, and metric Monsieur wants measured.
2. Confirm the intended operation is read-only. If a consuming run is needed, use the smallest deterministic control prompt and treat the explicit user request as authorization for that run only.
3. Check the browser automation service health before cookie handling.
4. Extract only the target domain's authentication cookies through the approved credential path. Keep decrypted values in memory or a restrictive temporary file; never print them.
5. Inject into a uniquely named temporary browser session and verify authentication using a non-sensitive account/plan label or dashboard element. `N` cookies injected is not authentication evidence.
6. Navigate to the real product surface. A route containing a product name may be a marketing page; verify the visible mode, model, and composer before measuring.
7. Open the native Usage/Plan/Account surface and record the relevant visible baseline lines, including the reset window and the exact label of the counter.

### 2. Use the current Camoufox-Max contract when it is the active browser

For the active host-side service, first check `GET http://127.0.0.1:9377/health`. The maintained contract uses JSON `POST` routes such as `/session/cookies`, `/tab/new`, `/tab/navigate`, `/tab/snapshot`, `/tab/click`, `/tab/type`, `/tab/evaluate`, `/tab/close`, and `DELETE /sessions/<temporary-user-id>` for final context cleanup.

The cookie endpoint expects an envelope:

```json
{
  "userId": "temporary-usage-check",
  "cookies": [
    {"name": "...", "value": "...", "domain": "...", "path": "/"}
  ]
}
```

Do not send the raw cookie array. The server reads `req.body.cookies`; a raw array produces an `expected array, got undefined`-style error. Keep the temporary identifier unique, inject only the target domains, and delete the complete session at the end.

### 3. Navigate and interact defensively

1. Take a fresh semantic snapshot after navigation and after every state-changing click/type action.
2. Use a ref from the newest snapshot. Refs can rebind or disappear when a SPA rerenders.
3. Prefer an exact visible label plus role over the first generic match. Large applications commonly expose duplicate unlabeled sidebar controls and the actual labeled control.
4. A successful click response is not proof that the UI changed. Wait for the modal/tab to settle, snapshot again, and verify the new state.
5. If a transition returns HTTP 500, do not repeat the same ref blindly. Capture the current state, discover the fresh ref, and continue from there.
6. Roles may vary between implementations. A visible `Usage` control can be emitted as a tab, generic node, or nested text; match the label first and use role as a secondary signal.
7. For values hidden from the semantic snapshot, evaluate a narrowly scoped DOM expression against the visible settings dialog. Filter to terms such as `usage`, `limit`, `credits`, `weekly`, `reset`, `remaining`, or `plan`; never dump the complete body or account history.

### 4. Measure a controlled run only when authorized

1. Record the exact pre-run metric and the active model/mode.
2. Send one minimal prompt that cannot trigger tools, navigation, file changes, messages, purchases, or account settings. Do not use a real business task as the calibration run.
3. Wait for an actual completion state. Do not detect completion because a keyword such as `OK` appears in the prompt; the user's text is part of the DOM and can create false positives. Use the product's answering/stop-control transition and verify the assistant response itself.
4. Re-open the Usage panel after a full page reload and record the same metric. A SPA can retain stale usage state in memory.
5. If the value is unchanged, report “the displayed metric remained unchanged after one completed run.” Do not translate that into “the run was free,” “zero tokens,” or “zero credits” without a first-party statement.
6. If exact marginal cost matters, explain that one run and one generic counter are insufficient; propose a small number of standardized runs only after Monsieur explicitly authorizes further consumption. Never automatically spend more quota to improve statistical confidence.

### 5. Interpret and report

Keep these fields separate:

- **Account/plan evidence**: the non-sensitive label proving which account and plan were opened.
- **Surface evidence**: the visible mode and model used for the control run.
- **Baseline**: exact displayed metric and reset text before the run.
- **Run result**: completion evidence and the minimal assistant response.
- **Post-run**: exact displayed metric after reload/reopen.
- **Conclusion**: only the comparison supported by those observations.

If the panel shows both a credit balance and a weekly/rolling reset, report both and state that they are distinct unless the UI defines their relationship. If the authenticated session cannot be established, report `AUTH_UNAVAILABLE`; if the transport/browser fails, report `CHECK_ERROR`; do not turn either into a quota value.

### 6. Mandatory cleanup

Always clean up in a `finally`-equivalent path:

- delete local cookie JSON, wrapper payloads, copied browser databases, snapshots, and logs that contain account material;
- delete the remote copied browser database;
- close individual tabs when appropriate;
- delete the temporary browser session so its context cookies are destroyed;
- verify cleanup with metadata-only checks.

Do not close or kill Monsieur's native browser, do not use his main-browser CDP for navigation, and never use `pkill` as browser cleanup.

## Failure patterns to avoid

- **Raw cookie payload**: send `{userId, cookies}`, not `cookies` alone.
- **Marketing route mistaken for product UI**: verify the live authenticated mode; product paths can redirect to public landing pages.
- **Stale refs**: snapshot after navigation and transitions; never hardcode an old ref.
- **Generic duplicate control**: choose the labeled account/profile control, not the first “open menu” node.
- **Premature completion**: `OK` in the prompt is not an answer; verify the stop/answering state.
- **Cached Usage panel**: reload and reopen before the post-run reading.
- **Metric overclaim**: unchanged credits do not prove zero cost.
- **Unrequested escalation**: never click reset, buy credits, enable auto-reload, upgrade, or change billing settings during a read-only check.
- **Secret persistence**: do not leave cookie exports or authenticated snapshots in `/tmp` or a durable skill reference.

## Verification checklist

- [ ] Live health check succeeded.
- [ ] Target account/plan verified without exposing secrets.
- [ ] Correct product surface, mode, and model verified.
- [ ] Baseline metric and reset text recorded from the live Usage/Plan UI.
- [ ] Any consuming run was explicitly authorized and minimal.
- [ ] Completion verified by UI state and assistant response, not a prompt keyword.
- [ ] Post-run metric re-read after reload/reopen.
- [ ] Conclusions distinguish unchanged display from zero cost.
- [ ] Temporary tabs, session, cookie files, copied DB, and snapshots cleaned up.

## References

- `references/codex-usage-check.md`: condensed evidence and troubleshooting from a verified ChatGPT Work/Luna Max quota probe, including the exact Camoufox-Max wrapper/ref/completion pitfalls.

## Related skills

- `authenticated-session-fallbacks`: recover authenticated access without bypassing MFA or account security.
- `webtop-authenticated-browsing`: extract/inject cookies and interact with authenticated browser surfaces.
- `camoufox-max-api-current`: current host-side Camoufox-Max endpoint contract.
- `vault-lookup`: secret lookup and redaction conventions.
