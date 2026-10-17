---
name: bitwarden-logins
description: Create accounts, log in, and handle 2FA on websites with Monsieur's Bitwarden — autonomously, without ever seeing or typing a password or code. Use for any sign-up, login, password, authenticator code, or code received by e-mail / message.
version: 1.2.0
author: W.Alter
metadata:
  hermes:
    tags: [bitwarden, login, password, 2fa, totp, otp, sign-up, browser, credentials, addy, alias, email, beeper]
---

# Logins with Bitwarden (plugin walter-secrets)

Monsieur's decision (2026-10-02): you use all his Bitwarden logins autonomously — never ask him for a password, never
type one, never put one in chat. Values are filled server-side and masked in every tool result.
Plugin `walter-secrets` is enabled in Hermes since 2026-10-16. If the `secret_*` tools are missing, check
`hermes plugins list` first.

## Log in to a site
1. `secret_search(query="site name or domain")` → item `id` (handle = `bw:<id>`), username, URLs.
2. Open the login page, `browser_type` the username yourself.
3. `secret_fill(handle)` → password filled. Submit.
4. Code asked? Pick the case:
   - **Authenticator key saved in Bitwarden** → `secret_fill(handle, field="totp")`. Submit.
   - **Code sent by e-mail or by message** (WhatsApp, Telegram, LINE… through Beeper) → `secret_otp(site="<site name
     or domain>")`: waits up to 2 min for a message from that site received in the last 10 min, then fills the code
     field. Submit. Do not read the mailbox or chats yourself for this: the tool never shows the code or the message.
   - **Code by real SMS** → not available (Beeper has no SMS account): ask Monsieur for the code.
   - **Code from an authenticator app outside Bitwarden** (Google Authenticator, Authy, the site's own app on his
     phone) → you cannot read it: ask Monsieur for the code. Afterwards, offer to move that account's 2FA key into
     Bitwarden (see « 2FA by authenticator app ») so the next login is automatic.
   - **Push approval on his phone** → ask Monsieur to approve.
5. `secret_fill` / `secret_otp` refuse when the page is not the item's / the named site: this is anti-phishing.
   Check the address. If it is genuinely the same site on another domain, add the URL to the item — never bypass.

Terminal / API flows: `$(walter-secret otp <site> [minutes] [timeout])` inside the command (never print it).

## Create an account
0. E-mail: by default a dedicated **addy.io alias** (Monsieur's choice, 2026-10-16), not his real address. Key:
   Bitwarden item « W.Alter · addy » (id `5de2210f-5f2e-45bc-8527-81c54760dc84`), field `api_key`.
   ```bash
   curl -s -X POST https://app.addy.io/api/v1/aliases \
     -H "Authorization: Bearer {{bw:5de2210f-5f2e-45bc-8527-81c54760dc84:api_key}}" \
     -H "Content-Type: application/json" -H "Accept: application/json" -H "X-Requested-With: XMLHttpRequest" \
     -d '{"domain":"earndeel.anonaddy.com","format":"custom","local_part":"<site>-<4 random chars>","description":"<Site> — created by W.Alter"}'
   ```
   → `data.email`. Use `earndeel.anonaddy.com` (unlimited on the free plan; random `anonaddy.com/.me` aliases are
   capped at 10, 10 MB of mail per month). Real address only when Monsieur asks, or for identity-bound accounts
   (bank, administration, Apple, Google). Mail to the alias lands in his Gmail, so `secret_otp` sees its codes.
1. Open the sign-up page, `browser_type` the e-mail/username.
2. `secret_create_login(username=..., label="Site")` → strong password generated, login saved in Bitwarden BEFORE
   submitting, password + confirmation fields filled. Submit. Symbols rejected → `symbols=false`; limits → `length=`.
   Note the alias in the item's notes.
3. Confirmation code by e-mail → `secret_otp(site=...)`. Confirmation link → open it from the mail tools.

## 2FA by authenticator app (preferred: fully automatic afterwards)
Site offers it → accept, click « show key / can't scan » if only a QR code is shown, `secret_capture_totp(handle)`,
then `secret_fill(handle, field="totp")` to confirm.

## Passkeys
Passkeys live on Monsieur's devices (Bitwarden in Brave / phone) and need his fingerprint or face: you cannot use
them. Site asks for a passkey → tell Monsieur to approve on his device, or use the password + code login if offered.

## Do not
- Use `browser_vault_fill` / `browser_vault_enter_code` / `browser_vault_save_login` on Camofox: they need a
  Chromium CDP session and save to the local vault, not Bitwarden. Use the `secret_*` tools above.
- Read a password with `secret_reveal` to type it: use `secret_fill` (or `{{bw:<id>:password}}` placeholders).
- Search the mailbox or chats to copy a code by hand: use `secret_otp`.
