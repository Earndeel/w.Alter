---
name: telegram-delivery-operations
description: Use when delivering Telegram media or rich messages.
tags: [telegram, media, bot-api, rich-messages, formatting]
metadata:
  hermes:
    tags: [telegram, media, bot-api, rich-messages, formatting]
---

# Telegram Delivery Operations

Use this umbrella for Telegram image/file delivery, structured rich messages, tables, and delivery verification.

## Media routing

Use Hermes' `MEDIA:/absolute/path` marker for the default native delivery path. If it fails silently, make one deliberate fallback to the Bot API and verify the JSON `ok` flag and `message_id`; do not loop on the same silent marker. Use `sendDocument` for original-quality files and `sendPhoto` when compression is acceptable. Keep captions within the active limit and split long text deliberately.

## Rich formatting

Distinguish legacy `sendMessage` Markdown/HTML from Rich Messages. A pipe table rendered literally means the legacy route was used, not that structured tables are impossible. Check the active adapter/config and current official contract before selecting rich blocks; when unavailable, use a narrow HTML or preformatted fallback and label it honestly.

Keep headings short, units explicit, and phone-width tables readable. Preserve distinctions such as per-second, per-image, and per-video costs instead of normalizing away their meaning.

## Safety and verification

Resolve bot tokens through the configured secret source without printing them. Verify the actual rendered Telegram message or media receipt, not merely an HTTP acceptance, and keep recipient/chat routing separate from content formatting.

Exact image, chat-ID, and Rich Message recipes are routed in `references/curator-telegram-archive-routes.md`.
