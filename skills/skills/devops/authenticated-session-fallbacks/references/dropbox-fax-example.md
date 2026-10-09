# Dropbox Fax / HelloFax Session Probe

This reference records a reusable read-only probe pattern for Dropbox Fax access.

## First-party surfaces

- Login surface: `https://app.hellofax.com/account/logIn`
- Native Dropbox OAuth surface: `https://www.dropbox.com/oauth2/authorize`
- Gmail/Google SSO may show a chooser, then a passkey challenge even when Google cookies are valid.

## Probe sequence

1. Extract Mac Brave cookie metadata and decrypt values only in the local process when the key is already in the approved vault.
2. Filter to `.hellofax.com`, `app.hellofax.com`, `.dropbox.com`, and the selected SSO provider.
3. Inject into an existing Webtop Chromium CDP context; do not create a new browser context.
4. Navigate to HelloFax login and inspect title, URL, and body text.
5. If the page still offers `Sign in with Dropbox`, the Dropbox cookie set is not an authenticated HelloFax session; do not infer access from cookie expiry dates.
6. Try the native SSO button once. If it reaches an account chooser, select only the account clearly tied to the requested service. If it reaches a passkey/MFA challenge, stop.
7. Search the user's approved mailbox for `HelloFax`, `Dropbox Fax`, `fax number`, and sender-domain filters. Search each already-authenticated account narrowly; do not dump the mailbox.
8. Search Bitwarden by item name, URL, and username and print metadata only. If no credential exists, ask before password recovery.

## Observed failure modes to recognize

- Valid-looking `t`, CSRF, analytics, or Cloudflare cookies can coexist with a logged-out Dropbox OAuth page.
- Google cookies can open Gmail successfully while a third-party OAuth client still requires a passkey confirmation.
- Brave's live `Login Data` SQLite database may be locked; copy it to a temporary path before querying metadata.
- No authenticated dashboard or first-party receipt means the fax number is not verified and must not be guessed.

## Camoufox Max validation detail

The active Camoufox Max HTTP surface may accept cookies and create a tab without navigating it. A reliable read-only probe is:

1. `POST /session/cookies` with the filtered auth cookies; record only status and count.
2. `POST /tab/new` to obtain a `tabId`.
3. `POST /tab/navigate` with `https://app.hellofax.com/` explicitly; do not assume the `url` passed to `/tab/new` was applied.
4. After the SPA settles, `POST /tab/evaluate` with a non-secret expression returning `location.href`, `document.title`, `document.readyState`, and a bounded `document.body.innerText` excerpt.
5. Confirm the dashboard shows the account greeting and `Send faxes` / `SEND A FAX` control. Stop before the send flow if the recipient, fax number, or final confirmation is missing.

An initial `about:blank` result after `/tab/new` is a navigation-state issue, not evidence that the cookies failed; explicitly navigating and rechecking resolves the ambiguity.
