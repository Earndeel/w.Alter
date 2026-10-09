# Authenticated browser recipes

Use this reference for provider-neutral depth behind `authenticated-workflows`; keep live provider selectors and URLs in the archived/provider-specific packages or a narrowly named companion skill when they are still needed.

## Session fallback and secret boundaries

1. Check target reachability from the actual egress before cookie work; TCP refusal or a country block is not an authentication failure.
2. Prefer the requested native/browser surface, verify the intended account, and inject only target-domain cookies into a temporary uniquely named session.
3. Prove authentication with final URL, title, account/entity text, and an application control—not cookie count or a successful injection response.
4. Prefer native SSO. Stop at MFA/passkeys/CAPTCHA/recovery and hand the user the native step. Never request, print, copy, or type the secret through the agent.
5. Search approved vault/mailbox sources narrowly and expose metadata only. Never dump credentials, cookie values, signed URLs, or complete page state.
6. Delete temporary browser/session artifacts after the run.

## OTP and challenge state machine

A fresh login creates a fresh OTP and consumes send quota. Reach the code screen first, then read the newest code from the approved mailbox and submit it in that same browser run. If the portal reports a send limit or a locked validator, stop retrying and report the wait/user-side retrieval path. A Cloudflare timer is not proof of clearance; a headed isolated browser may be the safe escalation when the target explicitly requires it.

## Portal documents

Use the portal's table as the source of truth. Confirm account/entity, jurisdiction, document type, date, and status before opening rows. Distinguish a listed row from a downloaded artifact. Capture the portal's own Download event, fetch signed URLs in the authenticated context when necessary, and validate host-visible bytes, MIME type, signature, and non-zero size before delivery. If a browser container hides the temporary download, use an authenticated host-side fetch rather than reporting a browser event as a file.

For recurring inbox checks, navigate directly to the verified inbox URL, wait for the SPA, return structured evidence (URL/title/row IDs/text), detect explicit empty-state text before parsing table nodes, and filter search controls out of the data set. Hash stable row IDs plus normalized text in a profile-local state file; baseline the first successful run without alerting and never reset a prior baseline on a blank or partial page.

## Authenticated media generation

Freeze `userId`, `tabId`, project, prompt, model/mode, and attachment order. Snapshot after every UI mutation. Verify each selected filename as a chip under the same composer ancestor as the prompt; visible library cards are not attachments. Require the live Generate/Create control to be enabled before clicking.

Treat credit confirmation as a separate authorization gate. Read the exact cost, request/verify one-time approval, re-snapshot, and never choose persistent future approval as a convenience. Observe a new media ID/current URL, ignore old failed cards, fetch the binary through the authenticated tab proxy, and verify container metadata and a preview frame when scene identity matters. A hidden `<video>`, currentSrc, or click response is not an artifact.

## Usage verification

Read the live Usage/Plan/Account panel for the intended account and current product surface. Record exact baseline labels and reset text. If authorized to run a control, use one minimal no-tool prompt, wait for the actual answer/stop-state (not a word in the prompt), reload the page, reopen Usage, and compare the same labels. Keep “displayed metric unchanged” distinct from “zero cost.” Cleanup includes temporary sessions, copied browser DBs, cookie JSON, snapshots, and logs.

## Private communities and encrypted history

Use evidence labels: `DIRECT_PRIVATE_CHANNEL`, `PUBLIC_FIRST_PARTY_FALLBACK`, `SEARCH_LEAD`, `BLOCKED_AUTH`, `VERIFIED_PRESENT`, `VERIFIED_EMPTY`, `UNVERIFIED_COVERAGE`, and `HISTORY_RESTORE_REQUIRED`. Do not turn a public changelog into private-community evidence or a date gap into “no messages.” When history restore requires a PIN/OTP/passkey, stop and resume only after the user confirms restoration; refresh account/thread/date-range evidence after recovery.

## Monitoring outcomes

A scheduler's success only proves process execution. For authenticated monitors:

- `NO_DATA`: the authenticated first-party page explicitly reports empty.
- `AUTH_UNAVAILABLE`: login/redirect/challenge prevented the check.
- `CHECK_ERROR`: transport, browser, script, or parse failure.

Keep state updates atomic, keep no-change stdout empty when the delivery contract requires it, verify the first real run, and remove/disable a monitor rather than sending false “empty” reports after session expiry.
