---
name: authenticated-session-fallbacks
description: "Recover authenticated access safely when browser cookies are present but do not establish a live session: validate auth, use native SSO, inspect approved vault/mailbox sources, and stop before MFA or account recovery side effects."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [browser, authentication, oauth, cookies, sso, vault, mailbox, read-only]
    related_skills: [webtop-authenticated-browsing, vault-lookup, web-service-browser]
---

# Authenticated Session Fallbacks

Use this class-level workflow when a user asks to access an authenticated web service and injected cookies or a persistent browser session do not reach the dashboard. The goal is to distinguish a valid authenticated session from merely present cookies, then recover access without silently changing account security.

## Trigger conditions

- The target redirects to login after cookie injection.
- A service offers native SSO but the session belongs to a different account or is incomplete.
- The requested data may exist in an approved mailbox, vault, or browser profile.
- A password reset, MFA prompt, consent grant, or other external side effect would be required.

## Workflow

1. **Confirm scope and account context.** Identify the service, the expected account, and whether the operation is read-only. If several accounts are available, do not silently pick an unrelated personal account; use the account that matches the user's stated business or service context, or ask.
2. **Validate the cookie result.** Inject only the target domain's cookies first. Navigate to the real application URL. Verify the title, URL, and visible body text. `cookies_extracted=N` is not evidence of authentication.
3. **Try native SSO.** Use the service's visible Dropbox, Google, Apple, Microsoft, or equivalent SSO button when the user explicitly asked to access the service. Follow an account chooser only when the account choice is unambiguous.
4. **Respect MFA and passkeys.** If the flow reaches a passkey, OTP, security key, or identity challenge, stop rather than bypassing it. Report the exact blocking stage.
5. **Check approved credential stores.** Search the configured vault/password manager by item name, URL, and username. Print metadata only: item name, username, whether a password exists, and length. Never print passwords, session tokens, or cookie values.
6. **Check an approved authenticated mailbox.** Search narrowly for service receipts, account notices, and subscription details. Prefer sender/domain and exact terms over a broad mailbox dump. Read only the minimum text needed to answer the user's request.
7. **Inspect browser saved credentials only as a read-only fallback.** Query a copy of the Chromium/Brave `Login Data` database because the live database is commonly locked. Do not restart or kill the user's browser. Decrypt a credential only inside the local process if the user authorized the login; never place it in chat output or logs.
8. **Stop before account recovery.** Password reset, email verification, security-setting changes, consent grants, sending an email, or creating a new credential are external side effects. Ask for explicit confirmation immediately before starting them.
9. **Verify the deliverable.** After successful authentication, extract only the requested field, cross-check it against the page or a first-party receipt, and report the source and account used. If blocked, say what was verified and what remains unavailable; do not fabricate a value.

## New-account registration and regional phone constraints

When Monsieur asks to create an account rather than access an existing one, treat registration as a separate, side-effectful workflow:

1. **Inspect the first-party signup flow before entering data.** Record whether the page offers mobile-number, email/account, SSO, or enterprise paths. Do not infer that an "Account" tab is email-only; it may still require a mobile number and SMS verification.
2. **Verify region support from the first-party UI, not marketing claims.** A visible `+86` may be fixed text rather than a country selector; inspect the live control and document the actual options before claiming international signup is supported. A third-party SMS-activation page listing a service and country is only a vendor claim, not evidence that the official signup accepts that country or that an OTP will be delivered. Keep those claims separate and do not turn vendor availability into a recommendation for the user's account.
3. **Use only a user-controlled contact channel.** Never substitute a support number, registered-agent number, rented SMS inbox, temporary number, or another person's phone without explicit evidence and authorization. A disposable number can strand the account and undermine recovery.
4. **Honor the named browser surface before authentication.** If Monsieur names Camoufox, stay in Camoufox and do not route the task to his Mac, Brave, or a native GUI as a workaround. Use the active Camoufox API to prepare and verify non-sensitive fields; do not request a Mac screen-control lease or switch surfaces unless he explicitly changes the target.

   **Use approved secret-manager mediation when explicitly authorized.** If Monsieur explicitly authorized the account creation and Bitwarden/browser integration can generate and autofill the credential without exposing it to the agent, use that sealed path: never hand-type, print, request, log, or emulate the autofill with a browser `type` action. Before invoking it, prove that the target is a user-facing/native browser where the Bitwarden extension or another sealed autofill mechanism is actually available; a headless DOM browser without that extension cannot perform this step safely. The agent may create the item through a non-displaying Bitwarden workflow (`bw generate` + `bw create item`) after the exact domain and username are selected, then verify only non-secret metadata. Store the login with the exact service URI and username; if only manual password entry is available, stop and hand the field back to Monsieur.
5. **Use an already-authorized mailbox for verification, without exposing codes.** First verify the Gmail token with the configured setup check, then search narrowly across all mail (`in:anywhere`) for the provider/domain and the service name. If a verification code is found, never have the agent type, copy, quote, or log it; Monsieur enters it directly unless the target provides a native sealed autofill that keeps the code hidden from the agent. A verification link or security confirmation is likewise handed back to Monsieur unless its action is explicitly approved and non-sensitive. Stop at passkeys, CAPTCHA, phone/identity/payment challenges, or an ambiguous account chooser; do not bypass them.
6. **Do not claim success from form progress.** Require a visible authenticated dashboard, account identifier, or first-party confirmation after signup. A successful password-manager save, sent verification email, or form transition alone does not prove registration completed.

For a concrete Volcano Engine example and the exact observed form fields, see `references/volcano-engine-registration.md`.

For the sealed Bitwarden autofill, secure item-creation, and browser-capability preflight, see `references/bitwarden-sealed-autofill.md`.

## Private community/server update checks

When Monsieur asks for the newest items in a private Discord, Slack, VIP community, or similar channel, separate direct channel evidence from a public first-party fallback:

1. **Locate the first-party sources first.** Find the provider's public changelog/API-updates page and its community/support entry point before attempting authentication.
2. **Treat join/authorization as a side effect.** `Authorize & Join`, `Connect Discord`, OAuth consent, or private-channel creation must not be clicked unless Monsieur explicitly asked to join or authorize the service.
3. **Classify the auth state.** If the browser shows a login screen or no authenticated server/channel list, label the private-channel result `BLOCKED_AUTH`; do not infer that the server has no announcements.
4. **Use a labelled fallback.** If the provider's own public updates/model pages are readable, report them as `PUBLIC_FIRST_PARTY_FALLBACK`, with the exact URL and source date. Never call them Discord findings unless the channel itself was opened and read.
5. **Offer only safe next steps.** Ask for a public invite or an already-authenticated session, never for passwords, Discord tokens, MFA codes, or recovery data.

See `references/private-community-update-checks.md` for the evidence labels, safe sequence, Kie.ai example, and output contract.

## Encrypted message-history recovery

When an authenticated messaging web app opens the contact/thread but reports that messages are missing or asks to restore chats, distinguish **account authentication** from **history availability**. A valid profile and visible contact do not prove that the requested date range is present.

1. Record the exact restore prompt and the verified account/thread. Report the local/API date coverage and any gap before attempting a fallback.
2. Do not ask Monsieur to paste a PIN, OTP, recovery code, or passkey into chat, and never type it yourself. Hand the sensitive restore action back to Monsieur in the native messaging client.
3. After Monsieur confirms that restoration is complete, create a fresh browser state, verify the account, thread, and requested date range, and only then read or analyze the messages/media.
4. If restoration is not completed, report `HISTORY_RESTORE_REQUIRED` with the verified coverage and stop. Never convert an unverified empty month into a negative claim about the conversation.

This pattern applies to Facebook/Messenger E2EE and other clients that locally protect chat history. See **`references/encrypted-message-history-recovery.md`** for the source-coverage checklist.

## Service-specific example: Dropbox Fax / HelloFax

Dropbox Fax uses the HelloFax application surface at `https://app.hellofax.com/`; do not substitute Dropbox Sign or a legacy Dropbox URL. Its native Dropbox SSO redirects through Dropbox OAuth at `www.dropbox.com/oauth2/authorize`. A cookie set containing `t`, CSRF, analytics, or Cloudflare cookies may still represent a logged-out state; confirm by checking whether OAuth asks for email/password. If the account is not available through native SSO, search the user's approved mailbox for `HelloFax`, `Dropbox Fax`, `fax number`, and service-domain senders before asking to reset the password.

When using the active Camoufox Max HTTP surface, a successful cookie injection is not enough: `POST /session/cookies` may return `200`, and `POST /tab/new` may initially leave the tab at `about:blank`. Explicitly call `POST /tab/navigate` with the exact HelloFax URL, wait for the SPA to settle, then verify `location.href`, `document.title`, and a small body-text excerpt through `POST /tab/evaluate`. Treat a visible account greeting and the `Send faxes` control as authentication evidence; do not proceed to transmission without the required recipient and final confirmation.

### Scheduled read-only monitor verification

For an authenticated-service watchdog (fax inbox, portal documents, billing state, or similar), separate **process success** from **business-result success**:

1. Treat the scheduler's `ok`/zero exit status as proof only that the script ran. It is not proof that the target page was authenticated or that the inbox was empty.
2. Validate authentication from the target page itself: final URL, page title, and a small body-text excerpt. A cookie count or successful cookie injection response is not authentication evidence.
3. Keep these outcomes distinct in diagnostics and user-facing reports: `NO_DATA` (authenticated page explicitly says empty), `AUTH_UNAVAILABLE` (redirect/login page), and `CHECK_ERROR` (transport/browser/script failure). Never report `NO_DATA` when the check reached `AUTH_UNAVAILABLE` or `CHECK_ERROR`.
4. When a session expires, stop or remove the monitor rather than silently delivering false reassurance. If the user asks to reverify and remove it, list scheduled jobs first, run one final check, inspect the target-specific diagnostic log/result, remove the exact job ID, then list again to verify removal.
5. Keep the probe read-only and clean up its temporary browser tab/session in a `finally` path. Do not reset a baseline or deduplication state after an authentication or transport failure.

For Dropbox Fax/HelloFax specifically, the received view is `https://app.hellofax.com/home/manage?filter=received`; an authenticated empty result is the page text indicating that no faxes have been received. A redirect to `https://app.hellofax.com/account/logIn...` means the fax status is **unknown**, not “no fax”.

### Dropbox Fax / HelloFax transmission workflow

For a user-authorized fax transmission, follow the live UI rather than guessing an upload or API endpoint:

1. **Refresh session material immediately before sending.** Re-copy the Mac Brave cookie DB, decrypt only target-domain auth cookies on the host, and inject them into a fresh uniquely named Camoufox session. Never print cookie values; delete the temporary cookie JSON and copied DB after the task.
2. **Verify the authenticated surface.** Navigate explicitly to `https://app.hellofax.com/`, verify the account greeting and `Send faxes`, and capture the tab ID returned by `/tab/new`. Never hardcode refs: snapshots reset after navigation and clicks.
3. **Upload through the live UI.** Start `Send a fax`, then wait for the selected filename to appear in `Selected documents`. If the HTTP browser wrapper has no file-path upload method, set the hidden `input[type=file]` with a browser-side `File` + `DataTransfer`, dispatch bubbling `input` and `change` events, and re-snapshot before pressing `Next`.
4. **Validate the recipient.** Fill the exact destination, verify the normalized country/number suggestion, and confirm that `Send document` becomes enabled. Do not select cover pages, color, or other extras unless requested.
5. **Confirm the external side effect.** Click the send button only after explicit user authorization. A first-use modal may ask for sender name/preferences; preserve already-correct values and confirm its separate `Send document` button.
6. **Verify the result independently.** Require the visible `Your document has been sent!`, the recipient in the sent row/details, and a document ID or stable download/preview handle. `Sending` means HelloFax accepted the fax for processing; it is not proof of IRS delivery.

See `references/dropbox-fax-send-workflow.md` for the tested Camoufox Max interaction recipe, hidden-file-input upload pattern, and post-send verification fields.

## Safe browser database pattern

When checking saved credentials, copy the database first and query only metadata:

```text
copy the profile's Login Data database to a temporary file
query origin_url, username_value, and password presence/length on the copy
```

A live `Login Data` database being locked is normal while the browser runs. The correct fix is to query a temporary copy, not to terminate the browser.

## Pitfalls

- Do not treat non-expired cookies as authenticated cookies.
- Do not inject Cloudflare clearance cookies across browsers; they are fingerprint-bound.
- Do not select a convenient SSO account merely because it is already visible.
- Do not turn a failed SSO/passkey flow into a silent password reset.
- Do not use a service's customer-support number or a registered-agent number as the user's contact number without evidence that it belongs in the requested field.
- Do not report a number, ID, or account detail unless it was observed in the authenticated service, a first-party message, or an authoritative document.

## Verification checklist

- [ ] Account identity matches the requested service/business context.
- [ ] Authentication is confirmed by dashboard content, not cookie count.
- [ ] Any MFA/passkey boundary is reported without bypass.
- [ ] Vault/mailbox searches exposed no secrets.
- [ ] No recovery email, credential change, consent grant, or message was sent without confirmation.
- [ ] Requested value is cross-checked against a first-party source.

## References

- `references/dropbox-fax-example.md`: read-only Dropbox Fax/HelloFax probe, SSO boundaries, mailbox and vault fallback.

## Related skills

- `webtop-authenticated-browsing`: cookie extraction and browser/CDP navigation mechanics.
- `vault-lookup`: secret lookup and redaction conventions.
- `web-service-browser`: one-shot web-service navigation and login fallback patterns.
