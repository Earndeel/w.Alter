# Klaviyo Unsubscribe Pages — Known Limitations

Klaviyo (used by many marketing email senders) hosts unsubscribe pages at `manage.kmail-lists.com`. These pages are **fully interactive** — they cannot be completed via HTTP POST or simple scraping.

## What the page does

1. Renders a form via JavaScript requiring the user to type their email address
2. Requires a click on the "Unsubscribe" button
3. Some variants show a "You've been unsubscribed" confirmation; others show preference checkboxes first

## What doesn't work

| Method | Result |
|--------|--------|
| `curl GET` the link | Returns page shell with no confirmation (JS-driven) |
| `curl POST` with email + list params | 200 OK but no actual unsubscription occurs |
| `scrapling_fetch` / `scrapling_bulk_get` | Extracts static text only ("Enter the email you want to unsubscribe*", "Something went wrong") — forms are JS-rendered |
| `scrapling_stealthy_fetch` with `wait` | Same — page content is static in the fetcher output |

## Workarounds (in preference order)

1. **Mark sender as SPAM via Gmail API** — immediate, stops inbox clutter, trains Gmail's spam filter:
   ```bash
   $GAPI gmail modify MESSAGE_ID --add-labels SPAM
   ```

2. **Create a Gmail filter** — auto-route future emails to spam/trash:
   Go to Gmail Settings → Filters → Create new filter → `from:interested@incauthority.com` → "Delete it" or "Mark as spam"

3. **Open in a real browser** — give the user the unsubscribe URL directly:
   ```
   https://manage.kmail-lists.com/subscriptions/unsubscribe?a=<params>
   ```
   They type their email and click Unsubscribe manually.

4. **Use Camoufox/headless browser** — if a full browser session is available, navigate to the page, fill the email field, and click submit. Note: standard Chrome headless may fail in certain environments.

## When this matters

Many marketing emails from LLC formation services (Inc Authority, ZenBusiness, etc.), SaaS newsletters, and ecommerce brands use Klaviyo. The unsubscribe link always follows this pattern: `manage.kmail-lists.com/subscriptions/unsubscribe?a=...&c=...&k=...&se=<url_encoded_email>&...`
