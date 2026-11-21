# Volcano Engine registration — observed form contract

Observed during a first-party signup check on 2026-08-08:

- Signup URL: `https://console.volcengine.com/auth/signup/`
- The page offers two tabs: **Mobile number** and **Account**.
- The **Account** tab still requires: username (5–50 characters), password, mobile number, and a 6-digit verification code.
- The mobile-number tab requires a phone number and SMS verification code.
- The visible country prefix is `+86` and, in the live browser check, it rendered as fixed text; no visible country selector or `+66` option was exposed. The only observed combobox was the page-language control.
- The official form therefore does not currently establish that a user-controlled Thai `+66` number is accepted. Do not claim that it works without a successful OTP request and first-party confirmation.
- Third-party SMS-activation pages that list Volcengine and foreign countries are vendor marketing claims, not evidence that the official form accepts those country codes; keep that evidence separate from the first-party registration result.
- No phone number, password, OTP, consent, or signup submission was entered during this check.

Safe handling:

1. Do not use rented, disposable, or third-party SMS numbers; they can strand account recovery and may violate the provider's controls.
2. The user must enter their password and received OTP/MFA code directly. Never request or type those secrets in chat or via the agent.
3. Treat the account as uncreated until the page shows a signed-in dashboard, account identifier, or first-party confirmation.
4. If the user lacks a usable number accepted by the service, report the registration blocker rather than inventing an email-only or bypass path.
