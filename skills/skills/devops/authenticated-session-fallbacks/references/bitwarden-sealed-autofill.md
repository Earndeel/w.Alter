# Bitwarden Sealed Autofill

Use this reference for account creation or login when Monsieur wants minimal intervention but the secret must remain inside Bitwarden.

## Contract

A sealed autofill means Bitwarden generates/retrieves and injects the credential while the agent never reads, copies, prints, quotes, logs, or types the value. User approval authorizes one exact autofill for one visible target domain; it does not authorize raw secret handling.

OTP/MFA codes, passkeys, CAPTCHA, recovery codes, payment data, and identity checks remain human steps unless the target offers a separate native autofill that keeps the value hidden from the agent.

## Preflight

1. Identify the exact service domain, account email/username, and signup/login URL.
2. Inspect the first-party form and fill only non-sensitive fields.
3. Prove that the active target is a user-facing/native browser with the Bitwarden extension or an equivalent sealed autofill path. A headless DOM browser without that extension can prepare and inspect non-sensitive fields, but it cannot perform the autofill safely.
4. Ask for a single explicit approval tied to the exact domain and item. If Bitwarden asks for its master password, vault unlock, passkey, or another security challenge, hand that step back to Monsieur.

## Create an item without exposing the password

When the exact email, username, and URI are selected and no item exists:

1. Unlock and sync Bitwarden with the configured helper (`bw-unlock --sync`).
2. Search items by name/URI and emit metadata only: item ID, name, username, URI, and whether a password exists. Never print the full item JSON.
3. Generate the password in the Bitwarden process (`bw generate`) and create the login from the Bitwarden item template (`bw create item`). Keep the password in process memory/stdin only; do not place it in a command argument, terminal output, browser field, screenshot, or chat.
4. Verify the created item by reading metadata only and checking `has_password=true`.
5. Use the native Bitwarden extension to autofill the exact visible domain. Never emulate this by calling a browser `type` action on the password field.

## After autofill

1. Re-capture the page because the form state and browser refs may have changed.
2. Verify that the expected non-secret field state is present and that the form is ready for the next human-controlled step.
3. Return the gate to Monsieur for OTP/MFA, CAPTCHA, email verification, passkey, legal terms, payment, or final security confirmation.
4. Verify signup success from a first-party authenticated dashboard, account identifier, or confirmation page. A saved Bitwarden item, sent verification email, or form transition alone is not proof.

## Camoufox preparation and handoff

When Camoufox is the explicitly requested surface and no Bitwarden extension is installed in that browser:

1. Health-check the active Camoufox Max server before creating a tab.
2. Create a tab with `POST /tab/new` (`userId`, `listItemId`), then navigate with `POST /tab/navigate` to the exact first-party signup/login URL.
3. Take `POST /tab/snapshot` and use only current refs. Fill non-sensitive fields with `POST /tab/type`; take a fresh snapshot after each mutation because refs may reset.
4. Verify the prepared values with `POST /tab/evaluate`, filtering out `input[type=password]` and returning only the expected email/username state. Never inspect or return the password value.
5. Leave the password and security controls untouched. Keep the tab prepared for a user-visible Camoufox/Webtop handoff or switch to a native Bitwarden-enabled browser only after Monsieur explicitly changes the requested surface.

The Camoufox API is a browser-control surface, not a password-manager integration. `bw get password` followed by `/tab/type`, Playwright `fill`, clipboard injection, or DOM assignment is direct agent secret entry and is forbidden.

- Never return or log the password, OTP, session token, cookie value, clipboard contents, or full item JSON.
- Do not expose a generated password through screenshots or DOM extraction.
- Do not select an account merely because it is the first matching Bitwarden item; ask when multiple identities remain.
- If the native extension is absent, stop at the password field and report the exact missing capability rather than falling back to direct typing.
