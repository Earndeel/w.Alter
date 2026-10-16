---
name: bitwarden-logins
description: Create accounts, log in, and handle 2FA on websites with Monsieur's Bitwarden — autonomously, without ever seeing or typing a password. Use for any sign-up, login, password or authenticator-code need in the browser.
version: 1.1.0
author: W.Alter
metadata:
  hermes:
    tags: [bitwarden, login, password, 2fa, totp, sign-up, browser, credentials, addy, alias, email]
---

# Logins with Bitwarden (plugin walter-secrets)

Monsieur's decision (2026-10-02): you use all his Bitwarden logins autonomously — never ask him for a password, never
type one, never put one in chat. Values are filled server-side and masked in every tool result.
Plugin `walter-secrets` is enabled in Hermes since 2026-10-16 (`plugins.enabled` in config.yaml). If the `secret_*`
tools are missing, check `hermes plugins list` before anything else.

## Log in to a site
1. `secret_search(query="site name or domain")` → item `id` (handle = `bw:<id>`), username, URLs.
2. Open the login page, `browser_type` the username yourself.
3. `secret_fill(handle)` → password filled. Submit.
4. Code asked? `secret_fill(handle, field="totp")` → current authenticator code filled. Submit.
   No authenticator key saved → the code comes by SMS/e-mail/app: ask Monsieur, or read the e-mail with the mail tools.
5. `secret_fill` refuses when the page origin is not one of the item's saved URLs: this is anti-phishing.
   Check the address. If it is genuinely the same site on another domain, add the URL to the item — never bypass.

## Create an account
0. E-mail: by default create a dedicated **addy.io alias** (Monsieur's choice, 2026-10-16) instead of his real address —
   it forwards to his Gmail, he can reply through it and disable it in one click. Key: Bitwarden item
   « W.Alter · addy », field `api_key` (placeholder `{{bw:W.Alter · addy:api_key}}` in terminal commands).
   ```bash
   curl -s -X POST https://app.addy.io/api/v1/aliases \
     -H "Authorization: Bearer {{bw:W.Alter · addy:api_key}}" -H "Content-Type: application/json" \
     -H "Accept: application/json" -H "X-Requested-With: XMLHttpRequest" \
     -d '{"domain":"earndeel.anonaddy.com","format":"custom","local_part":"<site>-<4 random chars>","description":"<Site> — created by W.Alter"}'
   ```
   → `data.email` is the alias. Use domain `earndeel.anonaddy.com` (unlimited on the free plan); random aliases on
   `anonaddy.com`/`anonaddy.me` are capped at 10 active. Free plan = 10 MB of forwarded mail per month.
   Use Monsieur's real address only when he asks, or for accounts tied to his identity (bank, administration, Apple,
   Google). Disable an alias: `PATCH`-less → `DELETE /api/v1/aliases/<id>` (deactivate) / `.../forget` (erase).
1. Open the sign-up page, `browser_type` the e-mail/username.
2. `secret_create_login(username=..., label="Site")` → strong password generated, login saved in Bitwarden
   (folder « W.Alter – Comptes créés ») BEFORE submitting, password + confirmation fields filled. Submit.
   Site rejects symbols → `symbols=false`. Length limits → `length=`.
   Note the alias in the item's notes so Monsieur knows which address the account uses.
3. Offer of 2FA by authenticator app → accept, click « show key / can't scan » if only a QR code is shown,
   `secret_capture_totp(handle)`, then `secret_fill(handle, field="totp")` to confirm.
4. Confirmation e-mail: it arrives in Monsieur's Gmail, sent to the alias — read it with the mail tools.

## Passkeys
Passkeys live on Monsieur's devices (Bitwarden in Brave / phone) and need his fingerprint or face: you cannot use
them. Site asks for a passkey → tell Monsieur to approve on his device, or use the password + TOTP login if offered.

## Do not
- Use `browser_vault_fill` / `browser_vault_enter_code` / `browser_vault_save_login` on Camofox: they need a
  Chromium CDP session and save to the local vault, not Bitwarden. Use the `secret_*` tools above.
- Read a password with `secret_reveal` to type it: use `secret_fill` (or `{{bw:<id>:password}}` placeholders in
  terminal/API calls).
- Put the addy key in a URL or print it: header only, via the placeholder.
