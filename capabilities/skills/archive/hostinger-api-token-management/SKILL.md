---
name: hostinger-api-token-management
description: Use when creating, replacing, or revoking a Hostinger API token for W.Alter, especially when Monsieur requests access without expiration.
---

## Inspect the current account and expiry options

1. Use W.Alter's browser and Walter Secrets interfaces. Never extract browser cookies or print credentials.
2. Open Hostinger's API settings in an authenticated Chromium session:
   ```bash
   walter-browser -e chromium -s <session> nav https://hpanel.hostinger.com/profile/api
   walter-browser -e chromium -s <session> snap 'Jetons API|Nouveau jeton'
   ```
3. Open the token list, then the new-token form. Inspect the expiration dropdown before generating anything. Hostinger offered « N’expire jamais » in the observed session; verify the current options live.
4. For Monsieur's explicit request for indefinite access, select « N’expire jamais ». Do not silently substitute a one-month token.

## Create and store the replacement

1. Give the replacement a recognizable name, such as `Walter-permanent`.
2. Obtain fresh element references with `snap` before clicking or typing:
   ```bash
   walter-browser -e chromium -s <session> snap 'textbox|Expiration|Générer'
   walter-browser -e chromium -s <session> click <current-ref>
   walter-browser -e chromium -s <session> ktype <name-field-ref> Walter-permanent
   ```
   References such as `e318` are session-specific; never reuse references from an earlier run.
3. Prepare a direct secret-storage path before generating the token. Read the current Walter Secrets procedure and API contract; transfer the generated value directly into the vault without returning it through tool output, screenshots, shell arguments, or logs. Do not dump the page after generation: it may contain the one-time token.
4. Store the replacement as a separate vault entry with its Hostinger purpose and verified expiration setting. Keep the old token working until replacement validation succeeds.

## Validate before revoking

1. Inject the replacement through `walter-secret exec`, using the binding syntax documented by the installed CLI. Run an authenticated, read-only Hostinger API request against a resource belonging to Monsieur. Report only HTTP status and a minimal resource identifier; never print authorization headers or the token.
2. Require successful authentication before revoking the previous token.
3. Return to the token list, identify the old token by its name and expiry, and delete only that token. Inspect the confirmation before accepting.
4. Refresh the list and verify that the permanent token remains and the temporary token is absent. Distinguish provider-side revocation from removal of an old vault entry.
5. Report the configured expiration, successful API validation, and revocation result. « N’expire jamais » describes the expiration setting; the token remains revocable.
