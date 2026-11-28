# Encrypted message-history recovery

## Purpose

Use this reference when a messaging API/cache and the first-party web client disagree about a requested date range. It covers E2EE restore prompts without bypassing account security.

## Decision path

1. **Resolve the exact thread first.** Record the platform, account, thread/contact identity, and whether the requested scope is read-only.
2. **Fetch the complete available history.** Follow every pagination cursor, deduplicate by stable message ID, and sort by timestamp. Record the oldest/newest timestamps plus a month/week histogram.
3. **Test coverage, not just matches.** If the target month is empty but lies inside a larger gap, classify it as `UNVERIFIED_COVERAGE`. Do not report “no messages” or “no media” until an independent source or an explicit first-party empty state verifies that period.
4. **Check the first-party client.** A successfully authenticated profile/contact is not proof that protected history is restored. Look for a restore notice, missing-history notice, or a PIN/passkey/one-time-code prompt.
5. **Gate sensitive recovery.** If restoration requires a PIN, OTP, recovery code, passkey, CAPTCHA, identity check, or security-setting action, stop and hand that step to the user. Never request the secret in chat, log it, copy it, or type it into the browser.
6. **Resume only after user confirmation.** Take a fresh browser capture/state, verify the account and exact thread again, and verify that the requested date range is now present before extracting content or media.
7. **Report blocked states precisely.** Use `HISTORY_RESTORE_REQUIRED` when the client says messages are missing and the user has not restored them. Include the verified local/API coverage and the missing scope; never turn the blocked state into a negative factual conclusion.
8. **Clean up sensitive artifacts.** Delete temporary cookie exports, copied browser databases, screenshots containing account data, and abandoned authenticated tabs/sessions after the handoff or completed check.

## Evidence labels

- `VERIFIED_PRESENT`: the requested messages/media are visible in the source and their timestamps are inside scope.
- `VERIFIED_EMPTY`: the authenticated first-party source explicitly states the requested scope is empty.
- `UNVERIFIED_COVERAGE`: the local/API source has a date gap or incomplete pagination.
- `HISTORY_RESTORE_REQUIRED`: the first-party client explicitly says history is missing and requires user-held recovery material.
- `AUTH_UNAVAILABLE`: the account/thread could not be authenticated or selected.

## Common mistakes

- Treating `hasMore=false`, a local cache boundary, or an empty API result as proof that the remote conversation never contained messages.
- Treating visible contact metadata or a current unread preview as proof that older E2EE history is available.
- Asking the user to paste a PIN/OTP into chat “just this once”.
- Reusing stale browser references after the user completes restoration.
- Leaving decrypted cookies or copied browser databases behind after a blocked attempt.
