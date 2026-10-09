---
name: stripe-checkout-automation
category: devops
description: Automate Stripe Checkout card entry via Playwright CDP — bypass Link, fill Elements, handle 3DS via Beeper.
---

## Trigger
When adding a payment card to any service that uses Stripe Checkout (Vast.ai, SaaS billing, Anthropic, etc.)

## Key Technique: Bypass Stripe Link
Stripe Link auto-saves and reuses cards. To enter a NEW card:
1. Click **"Pay without Link"** button immediately after checkout loads
2. Then click **Card accordion** via `document.querySelector('[data-testid="card-accordion-item-button"]')?.click()`
3. Fill fields in order: country → card number → expiry → CVC → name

## Alternative: Camoufox-Max (When Playwright CDP Unavailable)

When the webtop Chromium CDP is unreachable (Tailscale iptables issues, container networking), use the **camoufox-max** server (port 9378) with its keyboard/mouse endpoints.

### Approach

Stripe Elements are in **cross-origin iframes** — JS `evaluate` can't access their DOM. But Playwright's mouse/keyboard events operate at browser input level and bypass this restriction.

```bash
# 1. Navigate to billing page (must be logged in)
curl -s -X POST http://localhost:9378/tab/navigate \
  -d '{"tabId":"...","url":"https://platform.claude.com/settings/billing"}'

# 2. Click "Buy credits" → select amount ($5/$20/$100)
curl -s -X POST http://localhost:9378/tab/evaluate \
  -d '{"tabId":"...","expression":"/* click Buy credits button */"}'

# 3. Find Stripe iframe coordinates
curl -s -X POST http://localhost:9378/tab/evaluate \
  -d '{"tabId":"...","expression":"(function(){ var iframes = document.querySelectorAll(\"iframe\"); var result = []; for(var i=0;i<iframes.length;i++){ var name = iframes[i].name; if(name && name.includes(\"Stripe\")){ var r = iframes[i].getBoundingClientRect(); if(r.width > 50) result.push(name + \": x=\" + Math.round(r.left) + \" y=\" + Math.round(r.top) + \" w=\" + Math.round(r.width) + \" h=\" + Math.round(r.height)); } } return result.join(\"\\n\"); })()"}'

# 4. Click on card number iframe center
curl -s -X POST http://localhost:9378/tab/click-at \
  -d '{"tabId":"...","x":960,"y":537}'

# 5. Type card number (30ms delay per keystroke)
curl -s -X POST http://localhost:9378/tab/keyboard-type \
  -d '{"tabId":"...","text":"«secret:vault»","delay":30}'

# 6. Tab to expiry, type it
curl -s -X POST http://localhost:9378/tab/keyboard-press -d '{"tabId":"...","key":"Tab"}'
curl -s -X POST http://localhost:9378/tab/keyboard-type -d '{"tabId":"...","text":"05/31","delay":30}'

# 7. Tab to CVC, type it
curl -s -X POST http://localhost:9378/tab/keyboard-press -d '{"tabId":"...","key":"Tab"}'
curl -s -X POST http://localhost:9378/tab/keyboard-type -d '{"tabId":"...","text":"123","delay":30}'
```

### Stripe Iframe Naming Pattern

Stripe Elements use dynamically-named iframes: `__privateStripeFrame<random>`. They're NOT labeled by field type. To identify which iframe is which:
- The **first** iframe with w>100 and h>200 is usually **card number**
- The **second** iframe with w>100 and h>200 is usually **expiry + CVC**
- Stripe controller/metrics iframes (w=0 or h=1) are invisible — ignore them

### Pitfalls (Camoufox Path)

- **Click coordinates must be exact**: Stripe iframes are small. Off-by-20px hits the parent page instead of the iframe field.
- **Tab order inside Stripe iframe**: Card number → expiry → CVC. If Stripe shows a combined card/expiry/CVC field, the tab order is auto-handled by Stripe.
- **Rate limiting**: Same as Playwright path — ~10 failed attempts triggers 30min cooldown.
- **No frame content access**: Can't read iframe DOM to verify what was typed. Take a screenshot via `/tab/screenshot` to visually confirm.

## Card Fields (Stripe Elements)
Fields use standard IDs: `#cardNumber`, `#cardExpiry`, `#cardCvc`, `#billingName`, `#billingCountry`

**CRITICAL**: Use Playwright `type()`, NOT JavaScript `value` setting. Stripe Elements validate on keystroke events:
```python
card = frame.query_selector('#cardNumber')
card.click(click_count=3)  # select all
card.type('«secret:vault»', delay=20)
```

JS `value` assignment + `dispatchEvent('input')` does NOT trigger Stripe's internal validation — fields appear filled but submit fails silently.

## Country Field
`#billingCountry` is a `<select>`. Use Playwright's `select_option('FR')` — NOT JS value change.
Stripe auto-detects country from IP (e.g. Thailand for APAC servers). Must override BEFORE filling card.

## 3DS Verification Flow
After submit, Stripe sends verification code via SMS/iMessage. Retrieve from Beeper:
```bash
TOKEN=$(vault get beeper/token)
curl -s "http://100.127.150.1:23373/v1/chats/!0Yv8SCqY2O98k6y8V9wN:beeper.local/messages?limit=1" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].text'
# → "062680 is your Link verification code."
```
Enter in `#one-time-code` field, press Enter.

## Network Monitoring
Intercept `api.stripe.com` responses to track progress:
- `POST /v1/payment_methods` → 200 = card tokenized successfully
- `POST /v1/payment_pages/...` → 200 = checkout session updated
- If both return 200 but "Processing" persists → card may be declined at bank level (spending limits, geo-blocks)

## Rate Limiting
After ~10 failed Add Card attempts, Stripe rate-limits the checkout sessions. The "Add Card" button stops opening Stripe entirely. Wait ~30 minutes before retrying. Close all old Stripe tabs/pages first.

## Vast.ai Google OAuth Login
If session expired, re-login:
```python
page.click("text=Login", timeout=10000)
time.sleep(5)
page.evaluate("document.querySelectorAll('button').forEach(b => { if (b.innerText.includes('Continue with Google') && b.offsetParent) b.click(); });")
time.sleep(15)
# Handle Google consent in accounts.google.com frame
for f in page.frames:
    if 'accounts.google.com' in f.url:
        f.click("text=lucas.jouvencon@gmail.com", timeout=5000)
```

## Beeper Dependency
Stripe 3DS codes go to iMessage "stripelink" chat. Beeper Desktop MUST be running on the Mac (100.127.150.1:23373). If `connection refused`, the Mac app is closed — ask user to open it or use alternative retrieval.

## Pitfalls
- **Stripe Link interference**: When "Pay without Link" is clicked, Stripe still shows saved cards. The `#cardNumber` field may auto-fill with a Link-saved card instead of the intended one. Use `click(click_count=3)` + `Backspace` + `type()` to force-clear.
- **Country auto-detection**: Stripe detects country from server IP (e.g., Thailand for APAC servers). If the card is French, set `#billingCountry` to `FR` via `select_option('FR')` BEFORE filling card details.
- **SetupIntent hang**: After `POST /v1/payment_methods` returns 200, the `POST /v1/payment_pages/...` may also return 200 but the checkout stays "Processing" indefinitely. This is a webhook issue between Stripe and the merchant — NOT a card decline. The card is tokenized correctly but the merchant's backend never confirms the SetupIntent.
- **Session expiration**: Stripe checkout sessions expire. If 3DS code isn't entered within ~60 seconds, the session closes silently and redirects back to the merchant with no error. Get the 3DS code from Beeper BEFORE filling the form, or enter it within 10 seconds of submission.
- **Popup vs iframe**: Stripe checkout may open as a popup window (new page), replace the current page, or load as an iframe. Check all three: `context.pages` for popups, `page.url` for page replacement, `page.frames` for iframes.
- **Playwright click vs JS click**: React event handlers require Playwright's native `.click()` method. JS `dispatchEvent(new MouseEvent('click'))` may not trigger React's synthetic event system. Use `page.locator('[data-testid="..."]').click()` for React buttons.
- **Checkout opens as popup**: Stripe Checkout may open in a new tab instead of iframe. Listen for `context.on("page", ...)` or check `context.pages`.
- **Session expiry**: Stripe checkout sessions expire. Complete the flow within ~2 minutes.
- **Processing stuck**: If button says "Processing" for >60s, card is likely declined at bank level. Common causes: spending limits, international transaction blocks, insufficient funds. NOT a Stripe error — no alerts shown.
- **Saved Link card overrides**: If Link has a saved card, it pre-fills. MUST click "Pay without Link" first.
- **hcaptcha**: Stripe may show invisible hcaptcha. Usually auto-solves. If blocked, retry.
