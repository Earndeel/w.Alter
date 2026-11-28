---
name: google-workspace-multi-account
description: Use when adding a second Gmail account to Hermes.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [google, gmail, oauth, multi-account, hermes]
    related_skills: [google-workspace]
---

# Multi-account Google Workspace access

## Overview

Use this skill when Monsieur wants Walter to access a second or third Gmail/Google Workspace identity while keeping an already-authorized account usable. The standard Google Workspace helper stores one token at `HERMES_HOME/google_token.json`; treating that file as a shared multi-account store silently replaces the active identity. The safe unit is one account, one token directory, one OAuth pending-auth state, and an explicit routing decision.

This skill complements `google-workspace`; it does not replace its Gmail commands or OAuth troubleshooting reference.

## When to Use

- Monsieur says “give Walter access to this Gmail account” or asks to add another Google identity.
- A valid primary `google_token.json` already exists and must remain intact.
- Several Gmail accounts need separate read/send/modify authorization.
- An OAuth flow must be repeated for multiple accounts with the same Google Cloud client.

Do not use this for merely remembering email addresses. A remembered address is not an authorization, and do not report Gmail access until the account identity has been verified through the Gmail API.

## Core Rules

1. **One identity per token.** A Google OAuth token represents the Google account that granted consent. Separate consumer Gmail accounts require separate refresh tokens; do not assume a single token can search all inboxes.
2. **Never overwrite the primary token.** Preserve the existing `$HERMES_HOME/google_token.json`. Use an account-specific home such as `$HERMES_HOME/google-accounts/<slug>/` or a deliberately isolated Hermes profile.
3. **Separate pending OAuth state too.** `google_oauth_pending.json` contains the state and PKCE verifier for the current authorization. Generate and exchange each account’s flow with the same account-specific `HERMES_HOME`.
4. **Check the OAuth client before generating URLs.** For a Web client, set `GOOGLE_OAUTH_REDIRECT_URI` to an exact registered URI, including port and path. For an Installed/Desktop client, use its registered loopback URI. Never send a URL generated with an unverified default redirect.
5. **Email-only means `--services email`.** Request broader Calendar/Drive/Sheets/Docs scopes only when Monsieur explicitly needs them.
6. **Verification precedes completion.** After exchange, call Gmail `users.getProfile(userId="me")` and compare the returned `emailAddress` with the requested account. Also verify the granted scopes. A successful token write alone is not proof of access to the intended mailbox.

## Workflow

### 1. Establish the existing account

Run the standard Google Workspace setup check against the active home. If a token exists, verify its Gmail identity with `users.getProfile`; do not print token contents, refresh tokens, or client secrets. Record only the non-secret account identity and scope status needed for routing.

If Monsieur named an address that differs by one or more characters from the known primary address, preserve the exact requested spelling and treat it as a separate account until Google confirms otherwise. Do not silently correct it.

### 2. Prepare isolated account homes

Create one directory per requested account. Reuse the existing OAuth client secret by a protected symlink or a controlled copy; never duplicate or display token JSON unnecessarily. Ensure the directory is not the active primary home and contains no unrelated account token.

Example shape:

```text
$HERMES_HOME/
  google_token.json                 # existing primary account; untouched
  google_client_secret.json
  google-accounts/
    account-a/google_client_secret.json
    account-b/google_client_secret.json
```

The account directory must be writable by the setup script and have normal private permissions. Do not store credentials in `USER.md`, `MEMORY.md`, skills, chat transcripts, or URLs that are intended to be retained.

### 3. Inspect client type and redirect URI

Read only OAuth client metadata: whether the JSON contains `web` or `installed`, and the registered redirect URIs. For a Web client, select one exact registered URI and export it for **both** URL generation and code exchange:

```bash
export GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback'
```

If the client is Web and no usable exact URI is registered, stop and have the owner add one in Google Cloud Console before proceeding. Do not “try the default” first; that creates a misleading `redirect_uri_mismatch` flow.

### 4. Generate one consent URL per account

For each account, run the setup script with its isolated home and `--services email`. If several URLs are prepared, each one must have its own pending state file. A `login_hint` may be added to help Google select the intended account, but it does not replace checking the account shown on the consent screen.

Present the URLs one at a time when possible. Tell Monsieur to select the exact mailbox and to copy the complete callback URL after approval. A browser error at a localhost callback is expected when no local callback server is listening; the complete URL can still contain the authorization code needed for exchange.

### 5. Exchange and verify

Exchange the callback using the same account home, the same client secret, and the same redirect URI used to generate the URL. Never exchange account B’s callback while `HERMES_HOME` points at account A.

Then verify all of the following:

- setup reports an authenticated token in the account directory;
- Gmail `users.getProfile` returns the requested address exactly;
- the token has the scopes Monsieur requested;
- a harmless Gmail read probe succeeds, such as a bounded `in:anywhere` search;
- the primary account still returns its original identity from the primary home.

If any check fails, report the precise blocker. Do not claim that the account was added merely because Google displayed “allowed”.

### 6. Route future operations explicitly

The bundled `google_api.py` resolves its token from `HERMES_HOME/google_token.json`. Until an account-aware wrapper or tool exists, every operation must set the intended account home explicitly, or Walter must use a documented profile/account selector. Never switch accounts by renaming or replacing the primary token.

If Monsieur expects one Gmail action to search all connected accounts, design the routing first: accept an account selector, run the operation once per isolated token, label every result with its source address, and keep send/reply actions account-specific. Sending or modifying mail still requires the normal user confirmation rules.

## Common Pitfalls

1. **Interpreting “add my email” as a memory write.** Ask whether the request is authorization when access is implied. Store no address as proof of access.
2. **Overwriting `google_token.json`.** This loses the primary account from the default route. Isolate account homes before starting OAuth.
3. **Generating a Web-client URL with `http://localhost/`.** Inspect the client JSON first and use the exact registered URI, including port and path, on both auth steps.
4. **Mixing pending state and token directories.** Each account’s `--auth-url` and `--auth-code` must share the same `HERMES_HOME`; otherwise PKCE/state validation fails or the token lands under the wrong account.
5. **Trusting `login_hint`.** Google may still select another signed-in account. Verify with `users.getProfile`.
6. **Claiming success before a Gmail probe.** A token can be valid, partial, or authorized for the wrong mailbox. Verify identity and scopes.
7. **Saving secrets in durable context.** OAuth tokens, client secrets, passwords, and copied callback URLs do not belong in memory or skill files.
8. **Assuming multiple accounts are automatically available to every tool.** Single-token helpers remain single-token until routing is implemented and tested.

## References

- `references/multi-account-oauth-checklist.md` — concise commands and verification gates for a two-account Gmail authorization.
- `scripts/probe_accounts.py` — run to map every token directory (primary + `google-accounts/<slug>/`) to its Gmail address and granted scopes, read-only, before any multi-account audit or routing decision.

## Verification Checklist

- [ ] Existing primary token and identity remain unchanged.
- [ ] One isolated home exists per added Google identity.
- [ ] OAuth client type and exact redirect URI were checked before URL generation.
- [ ] URL generation and callback exchange used the same isolated home and redirect URI.
- [ ] Gmail profile identity exactly matches each requested address.
- [ ] Requested scopes are present and a bounded read probe succeeds.
- [ ] Future commands have an explicit account-routing mechanism.
- [ ] No token, password, client secret, or callback URL was persisted in memory or the skill library.
