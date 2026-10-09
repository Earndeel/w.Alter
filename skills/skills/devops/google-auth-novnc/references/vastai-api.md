# Vast.ai API Reference

## Authentication
- **Google OAuth**: Login via `cloud.vast.ai` → "Continue with Google" → auto-approves if Google session in persistent profile
- **API Key**: Stored in vault `vastai/api_key`, Bitwarden, `~/.config/vastai/vast_api_key`, `.env`
- **Session Cookie**: `auth_tkt` — works for browser-based API calls via `page.evaluate`

## API Key Management
```
# List keys (authenticated browser session required)
GET /api/v0/auth/apikeys/
Response: {"apikeys": [{"id": ..., "key": null, "key_type": "primary", ...}]}

# Create key (full key returned ONLY here)
POST /api/v0/auth/apikeys/
Body: {"name": "key-name"}
Response: {"success": true, "id": ..., "key": "full-hex-key", "permissions": {...}}
```
**Pitfall**: `/api/v0/apikeys/` returns 404. Correct path is `/api/v0/auth/apikeys/`.
**Pitfall**: Existing keys return `key: null` — full key only available at creation time.

## User Info
```
GET /api/v0/users/current/
Response: {"id": 347995, "username": "lucas.jouvencon@gmail.com", "api_key": "", "key_id": ...}
```

## CLI
```bash
vastai show user
vastai search offers 'gpu_name=RTX_4090'
vastai launch <offer_id>
```
Config: `~/.config/vastai/vast_api_key`

## Billing
- Stripe checkout for adding credit (embedded iframe on `/billing/`)
- "Add Card" opens Stripe Checkout — may be popup, page replacement, or iframe
- Stripe Elements use cross-origin iframes — PCI compliance blocks programmatic entry
- **SetupIntent hang issue**: Card tokenization succeeds (`POST /v1/payment_methods` → 200) but Vast.ai backend may not confirm the SetupIntent via webhook. Checkout stays "Processing" indefinitely. This is a merchant-side webhook issue.
- **"Add Credit" flow**: Modal with amount selection ($10/$25/$100/$200). Click "Add credit" opens Stripe checkout for payment (also saves card). May work when "Add Card" fails.
- **"Configure" button**: Opens "Automatic Billing" modal — sets top-up threshold/amount. Requires saved card first.
- For card addition issues: see `stripe-checkout-automation` skill

## User Details
- ID: 347995, Account: lucas.jouvencon@gmail.com (Google OAuth)
