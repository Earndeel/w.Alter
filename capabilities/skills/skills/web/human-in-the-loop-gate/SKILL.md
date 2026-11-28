---
name: human-in-the-loop-gate
description: Use before Monsieur handles a sensitive browser step.
version: 1.0.0
author: W.Alter
license: Proprietary
metadata:
  hermes:
    tags: [human-in-the-loop, approvals, credentials, browser, bitwarden, security]
    related_skills: [computer-use, bitwarden-integration, authenticated-session-fallbacks]
---

# Human-in-the-Loop Gate

## Purpose

Provide a clear, auditable handoff when browser or account work reaches a user-held secret or an external security/consent boundary. This gate coordinates human action; it never overrides Hermes or platform safety rules.

## Trigger conditions

Use the gate immediately before:

- entering or submitting a password, API key, OTP/MFA code, passkey, recovery code, or identity document;
- completing CAPTCHA, phone verification, email verification, OAuth consent, payment, or legal terms;
- clicking a security-sensitive confirmation that Monsieur must personally validate.

Never ask Monsieur to paste a secret into chat.

## Procedure

1. **Prepare first.** Navigate to the exact page, fill only non-sensitive fields, and leave the sensitive control ready. Do not type the secret.
2. **Show the native gate.** Call the `clarify` tool with exactly one clear question, for example:
   `La page est prête. Saisissez vous-même le mot de passe ou le code requis dans le navigateur, puis validez la reprise.`
   Use choices:
   - `J’ai terminé — reprendre`
   - `Annuler`
3. **Interpret the result.** `J’ai terminé — reprendre` means Monsieur says the manual step is complete; it is not permission for the agent to type the secret. `Annuler` stops the workflow without retrying.
4. **Refresh before continuing.** Capture a fresh browser state after approval because all prior refs may be stale. Verify the page URL, title, visible account state, and the next requested control before acting.
5. **Keep the gate short-lived.** Treat an approval as valid for one immediate continuation only and for no more than 90 seconds. If the state changes or the window expires, create a new gate.
6. **Verify the result.** Require first-party evidence of success (authenticated dashboard, account identifier, confirmation page, or stable task ID). Never infer success from a button click alone.

## Sealed Bitwarden autofill

A native Bitwarden autofill is distinct from the agent typing a password. It may be used only when all conditions hold:

- Monsieur has explicitly approved this exact autofill for the visible target domain;
- Bitwarden itself generates/retrieves and injects the value; the agent never reads, copies, prints, quotes, or logs it;
- the selected item, username, and domain are verified from non-secret metadata;
- the password is not exposed in a screenshot, browser DOM extraction, clipboard read, tool result, or chat;
- if the extension asks for the master password, a vault unlock, passkey, CAPTCHA, or another security challenge, hand that step back to Monsieur.

After a successful sealed autofill, the agent may continue with non-secret navigation and verification. A raw password retrieved through the CLI or vault is never placed into a form by the agent. OTP/MFA codes remain a human step unless the target provides a separate, explicitly approved native autofill that never exposes the code to the agent.

## Common pitfalls

- Treating the approval button as permission to type a password, OTP, API key, or payment data.
- Reusing stale browser refs after the human changes the page.
- Treating a successful form submission as proof that the account was created.
- Asking for a secret in chat instead of asking Monsieur to enter it directly in the browser.
- Continuing after `Annuler`, a timeout, an MFA failure, CAPTCHA, or an ambiguous page state.

## Verification checklist

- [ ] Non-sensitive fields were prepared before the gate.
- [ ] The sensitive value was entered by Monsieur, not by the agent.
- [ ] The approval was single-use and within 90 seconds.
- [ ] Browser state was freshly captured after approval.
- [ ] Success was verified from first-party page evidence.
- [ ] No secret appeared in chat, logs, screenshots, or tool output.
