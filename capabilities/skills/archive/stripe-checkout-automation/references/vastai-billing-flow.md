# Vast.ai Billing Flow Reference

## API Key Creation
```
POST https://cloud.vast.ai/api/v0/auth/apikeys/
Body: {"name": "W.Alter API Key"}
Cookie: auth_tkt=<session_cookie>
```
Response contains full key ONLY in the creation response. Store immediately.
Existing keys: `GET /api/v0/auth/apikeys/` — returns `{id, key: null, ...}` (key is null after creation).

## User Info
```
GET https://cloud.vast.ai/api/v0/users/current/
→ {username, balance, can_pay, id, ...}
```

## Payment Methods
```
GET https://cloud.vast.ai/api/v0/users/current/payment-methods/
→ [] (empty if no card saved)
```

## Billing Page Selectors
- Add Card: `[data-testid="billing-page-payment-methods-add-card-button"]`
- Add Credit: `[data-testid="billing-page-add-credit-button"]`
- Configure: button text "Configure" under Automatic Billing

## Google OAuth Login Flow
```
page.click("text=Login") → Google OAuth → accounts.google.com consent
```
Requires persistent Chromium profile with Google session.

## Stripe Checkout Behavior
1. Click "Add Card" → opens Stripe Checkout (popup, page replacement, or iframe)
2. Stripe Checkout shows Link + payment methods
3. "Pay without Link" → Card accordion → fill fields → submit
4. 3DS verification → code sent to iMessage "stripelink" chat
5. After code entry → "Processing" → redirect to Vast.ai billing
6. Card appears in payment methods if successful

## Known Issues
- Stripe sessions rate-limited after ~10 attempts
- "Processing" stuck = bank-level decline (no error shown)
- Country auto-detection from server IP (Thailand for APAC)
- Session expires if 3DS code not entered within ~60s
