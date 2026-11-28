---
name: authenticated-workflows
description: Use when accessing or verifying authenticated web services.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [authenticated, browser, portal, media, usage, frontend, credentials]
    related_skills: [authenticated-session-fallbacks, webtop-authenticated-browsing, vault-lookup]
---

# Authenticated Workflows

Class-level instructions for safely accessing, operating, verifying, and redesigning authenticated web services. Keep authentication state, user authorization, browser automation, artifact delivery, usage measurement, and frontend QA as separate gates; load the references for provider-specific recipes.

## When to Use

- A task requires a logged-in portal, SPA, media-generation UI, quota/usage surface, private community, or authenticated dashboard.
- Cookies, SSO, OTP, MFA, passkeys, vault credentials, signed downloads, or browser sessions are involved.
- An authenticated frontend must be redesigned without breaking IDs, session checks, routes, payloads, or accessibility.
- A generated/downloaded artifact or live usage value must be verified rather than inferred.

Do not use this to bypass MFA, CAPTCHA, account recovery, billing controls, provider terms, or a backend authorization boundary. Prefer an authorized official API when it provides the required operation and evidence.

## Non-Negotiable Boundaries

- Treat cookies-present, login-form-submitted, OTP-entered, dashboard-visible, artifact-downloaded, and business-result-verified as different states; never collapse them into “authenticated.”
- Keep passwords, OTPs, passkeys, recovery codes, cookies, bearer tokens, signed URLs, localStorage secrets, and complete authenticated snapshots out of chat, logs, screenshots, fixtures, and skill files.
- Use the user's named browser surface and account context; do not silently switch accounts, devices, browsers, or egress paths.
- Stop before MFA/passkey/CAPTCHA, password reset, consent grant, account recovery, payment, credit approval, message send, fax send, or other external side effect unless the user explicitly authorizes that exact action immediately before it.
- Use fresh state after navigation and every SPA mutation. Accessibility refs, DOM nodes, tabs, sessions, and signed URLs are disposable and must not be reused blindly.
- A visible row, success toast, HTTP 200 click response, hidden media element, cookie count, or cron `ok` status is not proof of the requested business result.
- Report evidence labels and blockers precisely: `AUTH_UNAVAILABLE`, `CHECK_ERROR`, `HISTORY_RESTORE_REQUIRED`, `NO_DATA`, `DIRECT_PRIVATE_CHANNEL`, or `PUBLIC_FIRST_PARTY_FALLBACK` are different outcomes.

## Four Gates

1. **Session gate:** intended account, domain, browser/tab, and authenticated page state are verified with non-sensitive evidence.
2. **Input/state gate:** prompt, selected files, filters, document rows, model/mode, or frontend fixture state are attached to the actual active surface, not merely visible elsewhere.
3. **Authorization gate:** any billable or account-changing action has explicit scope; one-time approval is not persistent approval.
4. **Result gate:** the current artifact, metric, UI behavior, or business state is observed and validated from the first-party surface or authenticated binary path.

A later gate cannot compensate for an earlier one.

## Authenticated Browser Procedure

### 1. Pre-flight reachability and identity

- Confirm the target URL is reachable from the required egress before extracting or injecting cookies; DNS resolution with TCP refusal is a network/geo block, not a cookie problem.
- Identify the intended account, service, project, entity, and browser backend. Check the browser service health and use a temporary uniquely named session when the workflow is read-only.
- Extract only target-domain credentials/cookies through approved vault or browser paths. Keep decrypted material in memory or restrictive temporary files; clean it in a finally path.
- Navigate explicitly to the real application URL. Verify final URL, title, account/entity label, and a bounded body excerpt. A project list, marketing page, `about:blank`, or login shell is not the requested surface.

### 2. Authentication and security prompts

- Prefer native SSO or the site's own login controls when the user requested access; choose an account only when its identity is unambiguous.
- Request a fresh OTP only after the current login reaches the OTP screen; submit it in the same session. Do not reuse a code from an earlier attempt or hammer a send-quota lockout.
- If the flow reaches MFA, passkey, CAPTCHA, recovery, or identity verification, stop and hand that step to the user. Never ask them to paste a secret into chat or type it through an agent browser.
- Use sealed password-manager autofill only when a native extension/integration is actually present. A headless DOM browser cannot safely emulate sealed autofill; never read a password and call `type`/`fill`.

### 3. SPA interaction and refs

- Take a fresh accessibility snapshot after navigation, click, typing, picker transition, upload, modal, or asynchronous rerender.
- Match exact visible text first and use role/semantic attributes second; duplicate generic controls and decorative cards are common.
- Verify state after every action. If a ref returns 400/500 or no visible change, discard it, snapshot again, and locate the current control.
- For selected media/documents, verify the chip/row/file under the same composer/table/form that will submit it. Library visibility does not equal attachment.
- For uploads, verify filename, MIME, size, and post-upload UI state; never disclose file contents or base64.

### 4. Document and media retrieval

- A listed document becomes a result only after the portal's own download action yields host-visible bytes.
- Capture signed URLs in process memory and fetch through the authenticated context when cookies are required; browser-local download events can point to an inaccessible container path.
- Validate HTTP status, content type, non-zero size, signature, and format metadata. For PDFs check a validator/page count when useful; for video check container, duration, codec, dimensions, frame rate, audio, and a preview frame when identity matters.
- Deliver the verified file path or attachment, not a transient URL or description.

### 5. Usage and quota verification

- Read the live first-party Usage/Plan/Account surface for the exact account, model/mode, metric, and reset window. Keep credits, rolling limits, purchased balance, and reset controls separate unless the UI explicitly relates them.
- A consuming calibration run requires explicit one-time authorization. Use the smallest deterministic no-tool prompt, record baseline, wait for the real completion state, reload/reopen the usage panel, and compare the same labeled metric.
- If a displayed metric is unchanged, report exactly that; do not call the run free, zero-cost, or zero-token without first-party evidence.
- Never click reset, upgrade, buy credits, auto-reload, or billing controls during a read-only check.

### 6. Private channels and history

- Direct private-channel findings require the authenticated channel itself to be opened and read. Public provider pages are a clearly labelled fallback, never a substitute silently presented as private content.
- For encrypted message history, distinguish account authentication from history availability. A visible profile/contact or `hasMore=false` does not prove requested date coverage. Use `HISTORY_RESTORE_REQUIRED` when the first-party client requests user-held recovery material.
- Do not infer “no data” from an auth failure, network block, partial SPA, missing-history prompt, or incomplete pagination.

### 7. Monitoring and cleanup

- For recurring inbox/document checks, use explicit outcomes: `NO_DATA` only for an authenticated first-party empty state; `AUTH_UNAVAILABLE` for login/redirect; `CHECK_ERROR` for transport/browser/script failure.
- Baseline stable item fingerprints atomically. A blank/partial page or auth failure must not erase the previous baseline. Script-only jobs should be silent on no-change and deliver through the verified target.
- Close tabs, delete temporary sessions, copied browser databases, cookie files, signed URLs, snapshots, and logs containing account material. Never use `pkill` to clean up a user's browser.

## Authenticated Frontend Surfaces

When redesigning login/dashboard/Studio pages, map page-local styles, shared CSS load order, body scopes, JavaScript IDs, routes, session checks, fetch/EventSource endpoints, generation payloads, and neighboring tests before editing. Define complete scoped tokens and one geometry contract; preserve DOM/API contracts and use CSS before markup changes.

Test anonymous login with an anonymous session fixture and authenticated pages with deterministic session/profile/data fixtures. Wait for async initialization before measuring. Measure computed foreground/background colors and target normal text at 4.5:1 and large text at 3:1. Assert no horizontal overflow, console/page errors, failed critical assets, broken interactions, or payload drift at desktop and mobile widths. Keep production unchanged until a local/preview visual review is approved, then verify deployed bytes rather than trusting a deploy command.

## Plugin/Provider/Deployment Scope

Keep local credential, control-plane secret binding, and deployed-runtime authentication as separate claims. A secret name, dry-run, or local 401 does not prove provider-wide failure. For browser plugins or packaged UI extensions, inventory bundled registry entries, active-profile disk plugins, and effective persisted enablement separately.

## Verification Contract

- [ ] Target egress, account, browser/tab, and final authenticated page are verified.
- [ ] Credentials and browser state stayed redacted and scoped.
- [ ] Fresh refs/state were used after every mutation.
- [ ] Every requested input is attached to the actual active form/composer/table.
- [ ] Any side effect or consuming action had explicit authorization and exact scope.
- [ ] The artifact/metric/business result was validated from the authenticated source.
- [ ] Auth failures, empty states, partial pages, and public fallbacks are labelled accurately.
- [ ] Temporary sessions and sensitive files were cleaned up.
- [ ] Frontend changes preserve contracts, pass contrast/responsive checks, and receive visual review before production.

## References

- `references/absorbed-source-routing.md` — mandatory routing to original procedures and support files when condensed rules are insufficient.

- `references/authenticated-browser-recipes.md` — consolidated portal, media, usage, session, monitoring, and evidence recipes.
- `references/authenticated-surface-qa.md` — authenticated frontend cascade, fixture, contrast, responsive, and deployment QA.
