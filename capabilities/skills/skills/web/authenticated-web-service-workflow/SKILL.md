---
name: authenticated-web-service-workflow
description: "Use when Monsieur requests a one-shot task on one of his web accounts, such as opening a service, checking a dashboard, or managing a plan, and the task may require a manual security step or continued browsing in his existing session."
type: workflow
requires: [web-service-browser, human-in-the-loop-gate, webtop-authenticated-browsing]
---

# Authenticated Web Service Workflow

Use this chain for a specific, authorized account task, not for public searches or unattended monitoring. Run the steps in order. Step 2 is a checkpoint on every run, but only prompts Monsieur if a sensitive step is present. Step 3 runs only if browser work or verification remains.

## 1. Open the service and establish page state

Load web-service-browser with skill_read. Resolve the intended first-party service, account, and requested outcome. Use the approved managed browser path with Monsieur’s existing login. If a particular browser or France exit is required, use the managed path only if that prerequisite is already verified; otherwise stop before authenticated navigation and report what needs checking.

Check that the page is on the expected site and that the visible account matches when an account indicator is available. Stop on an unexpected domain or account. If a sensitive control is reached, leave it untouched. Hand Step 2 the requested outcome, expected site and account, opaque session and tab references, current page state, and any pending sensitive action. Do not pass cookies, tokens, credentials, or other secrets.

## 2. Resolve the human checkpoint

Load human-in-the-loop-gate with skill_read. Check whether the next action requires Monsieur to handle a password, MFA, CAPTCHA, consent, payment, or another sensitive confirmation. If not, record that no gate was needed. If so, pause on the verified page and let Monsieur complete the action directly in the browser. Do not ask him to send secrets in chat or automate the challenge.

After Monsieur signals completion, discard old page references and inspect the same tab again. Verify the site, visible account state, and next control; his signal permits a fresh check, not a repeat submission. Stop on cancellation, expiry, failed verification, or ambiguity. Hand Step 3 the same session and tab references, the gate outcome, fresh non-secret page evidence, and the remaining authorized action. If the requested outcome is already verified, proceed directly to cleanup and reporting.

## 3. Continue in the authenticated browser

Load webtop-authenticated-browsing with skill_read. Confirm that the handoff still matches the active session, site, account, and requested scope. If Camoufox, Webtop CDP, or the France exit needs checking, verify the relevant prerequisite before continuing; stop if it cannot be confirmed rather than switching routes or accounts silently.

Perform only the remaining in-scope page interactions. Refresh page state after navigation before using any controls. If another sensitive boundary appears, return to Step 2 for a new gate. Verify the outcome from the service itself, such as the requested dashboard data, an updated plan status, or a confirmation page. A click alone is not evidence of success.

## Cleanup and reporting

Close only the tabs or temporary sessions created for this run, unless Monsieur asked to keep them open. Report what was verified, what changed, and any blocker or unconfirmed result. Keep secrets out of handoffs, reports, and captured evidence.
