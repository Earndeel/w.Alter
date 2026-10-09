---
name: telegram-image-delivery
description: "Send images and files to Telegram. Covers MEDIA prefix, sendPhoto, and sendDocument via Bot API."
tags: [telegram, image, screenshot, media]
---

# Telegram Image Delivery

Send images/files to Telegram when the Hermes `send_message` tool (text-only) is not enough.

## Method Selection

| Method | Quality | When |
|--------|---------|------|
| `MEDIA:/path` in response | Original | Default -- Hermes handles delivery |
| Bot API sendPhoto | Compressed | From execute_code/terminal |
| Bot API sendDocument | Original | Pixel-perfect screenshots |

## MEDIA prefix (simplest)

Include in response text:
```
MEDIA:/absolute/path/to/image.png
```
Hermes delivers natively on Telegram. No API call needed.
Only works from agent response, not from execute_code or terminal.

## Bot API (from execute_code)

Use Python requests to call Telegram Bot API endpoints:
- **sendPhoto**: `POST /bot{TOKEN}/sendPhoto` with `photo` file field + optional `caption` (max 1024 chars). Auto-compresses.
- **sendDocument**: `POST /bot{TOKEN}/sendDocument` with `document` file field. No compression -- use for full-resolution.

Token: extract from `/root/.hermes/.env` via Python file read. NEVER `hermes config set` (masks to `***`).

See `telegram-notification-delivery` skill for full Bot API patterns, token extraction, and chat ID lookup.

## MEDIA: silent failure → curl fallback

`MEDIA:/path` can fail **silently** — no error, no output, no delivery. If user says "rien" after a MEDIA: attempt, do NOT retry MEDIA:. Switch immediately to direct Bot API via curl in terminal:

1. Source the .env for the token, then POST to sendPhoto or sendDocument.
2. Parse the JSON response — verify `ok: True` and a `message_id`.
3. For full-resolution (no compression), use sendDocument instead of sendPhoto.

Recovery path: MEDIA: (1 try) → if no confirmation → curl sendPhoto/sendDocument → verify ok:True + message_id.

## Pitfalls

- **`send_message` tool is text only** — no media parameter exists. Use MEDIA prefix or Bot API directly.
- **sendPhoto compresses** — use sendDocument for pixel-perfect needs.
- **Caption limit 1024 chars** — send image first, then text separately if longer.
- **MEDIA: can fail silently** — no error feedback. If user confirms non-delivery, skip retries and go straight to curl Bot API. One attempt is enough.
- **Token from .env via bash `source`** — `python3 open()` works too but `source .env && var` is simpler in terminal one-liners.
