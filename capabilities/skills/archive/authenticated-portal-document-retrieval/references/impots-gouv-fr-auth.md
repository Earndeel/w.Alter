# impots.gouv.fr (particuliers) — authenticated document retrieval

Verified flow for downloading French tax documents (avis d'imposition / déclaration de revenus) from the personal tax portal. Auth mechanics validated 2026-08-07; full SPA + PDF download path NOT yet exercised end-to-end (rate limit hit before completion) — flag below.

## Access & credentials

- Portal: `https://cfspart.impots.gouv.fr/mesServicesWeb/`
- Credentials: stored in Bitwarden as multiple `*.impots.gouv.fr` items (duplicates; any works). Username = **numéro fiscal** (13 digits, e.g. `3027311582414`). Password is shared across all the dupes.
- The DGFiP email (`ne-pas-repondre@dgfip.finances.gouv.fr`, subject "Nouveaux documents disponibles") is a **notification only** — it contains no attachment. The user opted for online-only consultation: documents (avis d'imposition) live inside the espace, not in email.

## Auth flow (validated)

1. Fiscal number → field `#spi_tmp` (or `input[name='spi_tmp']`) → click button "Continuer".
2. Password → the **visible** field is `#pwd_tmp`. `input[name='pwd']` exists but is **hidden + disabled** — targeting it times out on visibility. Click "Se connecter".
3. OTP: arrives by email to the account's associated address from `otp@authentification.impots.gouv.fr`, subject "impots.gouv.fr - Code de sécurité". 6 digits, valid 30 min, displayed in the email body as "Votre code de sécurité est le suivant : 123456".
4. Submit via `input[name='otp']` (also matches `input[maxlength='6']`) → click "Valider le code de sécurité".

## OTP semantics — CRITICAL (validated)

- **Each login session mints a NEW code.** Logging in again invalidates reliance on the previous email's code; submitting an older code yields "Le code de sécurité renseigné est incorrect. Il vous reste N tentatives."
- Correct pattern: ONE Playwright run that (a) logs in, (b) reaches the OTP screen, (c) reads the *freshest* OTP from Gmail — query `from:otp@authentification.impots.gouv.fr`, filter by the email `Date` header to ≥ login time via `email.utils.parsedate_to_datetime` — and (d) submits it in the same running session. Do NOT pre-fetch a code before logging in.
- **Send-quota rate limit (validated):** every fresh login consumes a send slot. After a few logins the portal refuses new codes: "Le nombre maximum d'envois autorisés est atteint. Veuillez réessayer ultérieurement ou vous connecter via FranceConnect". Once blocked, submitting any code comes back "Le service est indisponible. Veuillez réessayer ultérieurement ou vous connecter via FranceConnect" (the validator itself is down for this account). Stop retrying immediately; wait (typically tens of minutes to hours) and then do the whole login → OTP → submit in a single session. Hammering a blocked challenge page is the exact anti-pattern.
- **Escape hatch when the quota is burnt:** stop automating and ask the user to fetch the document directly — same credentials, the portal emails them a code and they can grab the PDF in under a minute (validated 2026-08-07: user hand-retrieved the avis d'imposition PDF this way while the automated session was locked out). A user-side retrieval beats a third automated retry every time.

## Browser stack notes

- Native Hermes Camoufox browser handles navigation/typing fine but its `browser_console` **does not support JS evaluation** — so scripted auth must switch to Playwright.
- Install into the Hermes venv: `<venv python> -m pip install playwright` then `<venv python> -m playwright install chromium`.
- No captcha encountered. Chrome UA + `locale="fr-FR"` suffices.

## Secret handling (do not leak into transcript)

Write password and OTP to a 0600 temp file (`.impots_pw`, `.impots_otp`); the Playwright script reads them from disk via `pathlib` and returns only lengths/booleans. Never pass secrets as CLI args, tool-call text, or print them in page-text dumps. A localhost HTTP server that the page `fetch`es is NOT usable here (JS eval is disabled on the native browser).

## Downloading the avis d'imposition

Launch Playwright with `accept_downloads=True`; after a successful OTP you land in the espace particulier where "Avis d'imposition" holds the yearly avis (e.g. avis 2025 = revenus 2024). Trigger the portal's own Download, save to a host-visible path, validate PDF signature (`%PDF-`) + non-zero size before delivery.

## Status ledger (what is vs isn't validated)

| Step | Status |
|------|--------|
| Credentials valid (login reaches OTP screen) | ✅ validated |
| field names `spi_tmp` / `pwd_tmp` / `otp` | ✅ validated |
| OTP per-session invalidation + rate limit | ✅ validated |
| Fresh-OTP-read-in-same-run script | ⚠️ written, **not** run to completion (quota) |
| Post-auth SPA navigation + PDF download | ❌ not yet exercised — verify menu wording live |
