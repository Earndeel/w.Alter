---
name: stripe-dynamic-checkout
description: Create Stripe checkout sessions dynamically with on-the-fly pricing (no pre-created prices). Useful for variable credit packs or usage-based billing.
---

# Stripe Dynamic Checkout

## When to use
- Variable pricing (credit packs, usage-based)
- No pre-created Stripe Price objects
- Server-side checkout session creation

## Steps

### 1. Create price on the fly
```python
import urllib.request, urllib.parse, json

stripe_key = "sk_live_..."

# Create price dynamically
price_data = urllib.parse.urlencode({
    "unit_amount": int(amount_usd * 100),  # cents
    "currency": "usd",
    "product_data[name]": f"Credits ({credits})",
    "product_data[metadata][credits]": str(credits),
}).encode()

req = urllib.request.Request(
    "https://api.stripe.com/v1/prices",
    data=price_data, method="POST"
)
req.add_header("Authorization", f"Bearer {stripe_key}")
req.add_header("Content-Type", "application/x-www-form-urlencoded")

with urllib.request.urlopen(req, timeout=15) as resp:
    price = json.loads(resp.read())

price_id = price["id"]
```

### 2. Create checkout session
```python
session_data = urllib.parse.urlencode({
    "line_items[0][price]": price_id,
    "line_items[0][quantity]": "1",
    "mode": "payment",
    "success_url": "https://example.com/success",
    "cancel_url": "https://example.com/cancel",
    "metadata[client_id]": client_id,
    "metadata[credits]": str(credits),
}).encode()

req2 = urllib.request.Request(
    "https://api.stripe.com/v1/checkout/sessions",
    data=session_data, method="POST"
)
req2.add_header("Authorization", f"Bearer {stripe_key}")
req2.add_header("Content-Type", "application/x-www-form-urlencoded")

with urllib.request.urlopen(req2, timeout=15) as resp2:
    session = json.loads(resp2.read())

checkout_url = session["url"]  # Redirect user here
```

### 3. Webhook handler
```python
@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    event = json.loads(request.get_data(as_text=True))
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session["metadata"]
        client_id = metadata["client_id"]
        credits = float(metadata["credits"])
        
        # Add credits to client
        add_credits(client_id, credits, f"Stripe payment {session['payment_intent']}")
    
    return jsonify({"ok": True})
```

## Pricing formula
```python
raw_usd = credits * credit_value_usd  # e.g., 100 * 0.01 = $1.00
billed_usd = raw_usd * margin_multiplier  # e.g., 1.00 * 1.5 = $1.50
amount_cents = int(billed_usd * 100)
```

## 3DS Automation Loop (Beeper + Stripe Checkout)

When Stripe checkout triggers 3D Secure (SMS/iMessage code), automate the full loop:

### Flow
1. Click "Pay without Link" in Stripe checkout to bypass Link auto-fill
2. Click Card accordion (`[data-testid="card-accordion-item-button"]`)
3. Fill fields using Playwright `type()` (NOT JS `value` — Stripe Elements intercept JS):
   ```python
   card = f.query_selector('#cardNumber')
   card.click(click_count=3)  # select all
   card.type('«secret:vault»', delay=20)
   # Same pattern for #cardExpiry, #cardCvc, #billingName
   ```
4. Submit: `f.evaluate("document.querySelector('[data-testid=\"hosted-payment-submit-button\"]')?.click()")`
5. Wait 8s, check for "Confirm it's you" / "code sent" text
6. **Fetch code from Beeper immediately** (see below)
7. Enter code: `code_input.type(code, delay=30); code_input.press('Enter')`
8. Wait 20s for result

### Fetching 3DS Code from Beeper
```python
TOKEN = subprocess.run(['vault', 'get', 'beeper/token'], capture_output=True, text=True).stdout.strip()
CHAT_ID = "!0Yv8SCqY2O98k6y8V9wN:beeper.local"  # stripelink iMessage chat
r = subprocess.run(['curl', '-s', f'http://100.127.150.1:23373/v1/chats/{CHAT_ID}/messages?limit=1',
    '-H', f'Authorization: Bearer {TOKEN}'], capture_output=True, text=True, timeout=10)
msgs = json.loads(r.stdout)
codes = re.findall(r'\b\d{6}\b', msgs['items'][0]['text'])
code = codes[0]  # e.g. "062680"
```

### Pitfalls
- **Stripe Link auto-fills saved cards**: If user has a saved card in Link, it pre-fills instead of new card. MUST click "Pay without Link" first.
- **Card fields reset if filled too slowly**: Stripe Elements detect programmatic input and reset. Use Playwright `type()` with `delay=20` (fast but human-like).
- **Session expires if too slow**: The whole flow (fill → submit → 3DS → code → enter) must complete within ~90 seconds. Get code from Beeper BEFORE the 3DS page times out.
- **Country auto-detected from IP**: Server IP (Thailand) may cause card decline. Stripe doesn't always allow setting country to FR for a Thai IP card.
- **`createPaymentMethod` requires Elements**: Can't pass raw card numbers to `stripe.createPaymentMethod()` — PCI compliance forces using Stripe Elements iframes.
- **Vast.ai "Add Card" opens Stripe in iframe**: Not a popup or new tab. Check `page.frames` for `checkout.stripe.com`.
- **Beeper code freshness**: Always fetch `limit=1` (latest) and check timestamp. Old codes ( >2 min) may be expired.
- **`unit_amount` is in cents** — $1.50 = 150
- **Metadata must be string** — `str(credits)`, not `credits`
- **Prices are cached by Stripe** — creating many dynamic prices works but generates clutter; consider Payment Links for simpler cases
- **Webhook signature verification** — implement for production to prevent spoofing
