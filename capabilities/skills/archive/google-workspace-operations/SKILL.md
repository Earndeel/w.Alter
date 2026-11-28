---
name: google-workspace-operations
description: Use for Google Workspace accounts, Gmail, and routing.
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [google, workspace, gmail, oauth, multi-account, intelligence]
---

# Google Workspace Operations

Use this class-level skill for Gmail intelligence, multi-account Google authorization, account routing, and read-only Workspace workflows. Keep account identity, OAuth state, scopes, search results, and side effects separate because a valid token or a visible consent screen does not prove the intended mailbox is usable.

## Account and OAuth invariants

- Treat one Google identity as one token home, one pending OAuth state, and one explicit route; never overwrite the primary token to add another account.
- Inspect OAuth client type and exact registered redirect URI before generating a URL, and use the same isolated home/client/redirect for callback exchange.
- Request only the services/scopes required for the task; email-only work should not silently authorize Calendar, Drive, Sheets, or Docs.
- Verify `users.getProfile` and granted scopes after exchange, then run a bounded harmless read; token persistence or “allowed” is not completion.
- Preserve exact requested addresses and identifiers; do not silently normalize near-matches.
- Keep tokens, client secrets, callback URLs, signed links, OTPs, and tracking parameters out of logs, durable notes, prompts, and reports.

## Multi-account routing

Use an explicit account selector or isolated profile/home for every operation. Search, fetch, send, and modify actions must carry the source account; Gmail message IDs are account-scoped and a cross-account 404 is a routing signal. Search each authorized account independently and label findings by the confirmed profile address. Sending or modifying mail requires the normal side-effect approval in addition to account verification.

## Gmail intelligence

1. Define the date window, authorized accounts, read-only boundary, and opportunity categories.
2. Search `in:anywhere` with bounded, decomposed queries; do not infer absence from one complex zero-result query.
3. Page through actual message IDs, keep metadata-first, and fetch full MIME bodies only for shortlisted candidates.
4. Normalize plain text/HTML while preserving account, sender, subject, date, ID, and evidence; redact signed or magic URLs.
5. Classify each lead as concrete, incomplete, referral/affiliate, credit/discount/prize, historical/expired, or suspicious.
6. Check residence, language, device, work authorization, compensation unit, volume, deadline, privacy obligations, and duplicate-profile risk before ranking.
7. Report exact evidence, account source, confidence, blockers, and actions not taken. An invitation is not hiring, “up to” is not expected income, and “remote” is not worldwide eligibility.

## Completion contract

A successful Workspace operation proves the intended account identity, scopes, route, and requested read/write state. Report partial/blocked results explicitly and never claim cross-account access from a single-token helper.
