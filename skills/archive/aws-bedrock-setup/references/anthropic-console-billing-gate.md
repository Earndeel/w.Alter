# Anthropic Console Billing Gate for Marketplace SaaS

## The Problem

When trying to link an AWS account to Anthropic via the "Claude Platform on AWS" flow (Section 7c), the Anthropic Console at `console.anthropic.com` may block registration because the account is on the **Free Plan**.

### Symptom Flow

1. Accept Marketplace agreement for Fable 5 / Opus 4.8 (agmt-XXXXX accepted)
2. Attempt "Claude Platform on AWS" sign-up
3. Anthropic Console shows pricing page instead of provisioning
4. Console → Settings → Plans shows: "Free Plan"
5. Billing page at `console.anthropic.com/settings/billing` shows upgrade options

**Root cause**: The Marketplace SaaS registration provisions a new Anthropic organization. If the Anthropic account hasn't been upgraded from the Free Plan, the Marketplace offer cannot be consumed. The free plan doesn't qualify for paid Marketplace entitlements.

### The Fix

The Anthropic account must be upgraded to a paid plan (Pro $20/mo or Team $30/mo/person) BEFORE the Marketplace SaaS flow will work.

**Flow to upgrade**:
1. Navigate to `console.anthropic.com/settings/billing`
2. Login with the Anthropic account (earndeel@gmail.com)
3. **If redirected to a pricing/plan selection page**, this is the billing gate
4. Select a plan (Pro or Team)
5. Enter payment method
6. After upgrade, retry the "Claude Platform on AWS" sign-up

### Camoufox Automation Patterns for Anthropic Console

The Anthropic Console (`console.anthropic.com`) is a Clerk-authenticated React SPA:

**Login page selectors**:
- Email input: `document.querySelector('[data-testid="email-input"]')` or `input[name="identifier"]`
- Continue button: `.cl-internal-1ocx17p` (class-based) or `button[data-localization-key="formButtonPrimary"]`
- Sign-up link: `.cl-internal-t3b0qq` (class-based)
- Container: `.cl-signUp-root`

**Billing/pricing page selectors**:
- Plan cards: Usually `<button>` or `<a>` within plan card containers
- Radio buttons: Selectable via `.click()` directly
- Team plan = value=2 in radio group

**Pitfalls**:
- **Email verification OTP required** — Clerk sends a 6-digit code to earndeel@gmail.com
- **Gmail API NOT available** for earndeel@gmail.com — only lucas.jouvencon@gmail.com has OAuth configured
- **Code expires in ~90 seconds** — must retrieve and enter quickly
- **Each "Resend code" invalidates ALL previous codes**
- **Do NOT restart Camoufox** between entering email and entering the code
- **Gmail API access mismatch**: The AWS root email (earndeel@gmail.com) is different from the email with Gmail OAuth access (lucas.jouvencon@gmail.com). This makes automated OTP retrieval impossible without Beeper/Gmail forwarding.

### OTP Verification via Camoufox (Automated — Tested 2026-06-11)

The email OTP blocker is **NOT a hard blocker** if you have user cooperation. The full flow works:

1. **Navigate to login**: `https://console.anthropic.com/settings/billing`
2. **Enter email** in the Clerk login form (accessibility tree: `email-input` textbox)
3. **Ask user for the 6-digit code** — Clerk sends to earndeel@gmail.com
4. **Enter OTP code** in the verification field (snapshot shows `textbox "Enter your verification code"`)
5. **Email verified** → billing page loads
6. **Click "Buy credits"** → select amount ($5 minimum) → credit card modal appears (Stripe-style)

**Clerk SPA is Camoufox-friendly** — no Ant Design portal issues, standard accessibility tree.

### Billing Page Architecture

- URL: `console.anthropic.com/settings/billing`
- Requires Clerk authentication (email OTP flow)
- Plan selection is a separate page from billing details
- Payment via credit card only (no invoicing on Free/Pro plans)
- Team plan requires org name + 2+ seats minimum ($30/mo × 2 = $60/mo minimum)
- Pro plan = $20/mo, 1 user, enough for Marketplace linkage
- **Minimum credit purchase**: $5 (enough to upgrade from Free to paid plan)
- **Credit card modal**: Appears after clicking "Buy credits" — standard Stripe card entry form

### Stripe Payment via Camoufox — Iframe Limitation

**Problem**: The Stripe credit card form is embedded in a cross-origin `<iframe>`. Camoufox's `/tab/evaluate` endpoint cannot access iframe contents due to browser security restrictions. You CANNOT fill card number, expiry, or CVC programmatically.

**Workaround — Webtop Chromium (manual payment)**:
1. Open the webtop Chromium browser (Selkies on port 3001 or noVNC on port 3100)
2. Navigate to `console.anthropic.com/settings/billing` in the webtop browser
3. Log in with earndeel@gmail.com (same OTP flow)
4. Click "Buy credits" → select $5 → fill Stripe form manually in the webtop browser
5. Webtop Chromium has full access to cross-origin iframes — no restrictions

**Stripe Link pattern**: If the user has Stripe Link enabled, verification codes are sent to their Beeper chat (chat name "stripelink"). Retrieve codes via Beeper API using the vault-lookup skill pattern for Beeper token retrieval.

### "Setup failed: AWS account registration is incomplete or revoked"

This error appears during the "Claude Platform on AWS" → "Get started" → "Continue" flow. It means the Anthropic account (earndeel@gmail.com) is on the **Free Plan** — NOT that a wrong account was linked. No Anthropic account is linked to AWS until this flow succeeds. Fix: upgrade earndeel@gmail.com to paid plan via billing page ($5 minimum), then retry.
