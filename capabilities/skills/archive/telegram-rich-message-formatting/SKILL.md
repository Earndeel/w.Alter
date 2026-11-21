---
name: telegram-rich-message-formatting
description: Use when sending Telegram tables or Rich Messages.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [telegram, rich-messages, tables, formatting, bot-api]
---

# Telegram Rich Message Formatting

Use this skill when a Telegram response needs a table, structured comparison, headings, quotations, collapsible detail, or another layout beyond ordinary inline formatting.

## Core distinction

Telegram has two different formatting layers:

1. **Legacy `sendMessage` parsing** — `parse_mode=MarkdownV2` or `HTML`. Pipe-separated Markdown tables are not a native table object in this layer.
2. **Rich Messages** — the Bot API exposes structured rich-message objects, including `RichBlockTable` / table cells, through `sendRichMessage` and related rich-message methods.

Never use the limitation of legacy Markdown as evidence that Telegram cannot render tables. Check whether the Hermes Telegram adapter has Rich Messages enabled and whether the outgoing route actually uses the rich-message method.

## Workflow

1. Check the active Telegram configuration for `telegram.extra.rich_messages: true`.
2. Check the current official Bot API Rich Messages documentation before relying on a newly introduced object or method.
3. For structured output, prefer the gateway's native Rich Message conversion rather than manually sending pipe characters through legacy Markdown.
4. If the active adapter only exposes `sendMessage`, use an explicit fallback: HTML, or a monospace/preformatted aligned layout. Label the fallback honestly; do not call it a native table.
5. For a test, send a small table with a header row, two data rows, and explicit units, then verify the rendered Telegram message rather than inferring success from an HTTP acceptance alone.

## Data and legibility rules

- Keep column headings short and units explicit.
- Preserve distinctions such as `per second`, `per video`, and `per image`.
- Do not normalize a fixed per-video price to a per-second rate unless duration is explicit.
- For price comparisons, include model variant, resolution, input mode, credits, USD, and normalized clip cost only when valid.
- If a table is too wide for a phone screen, reduce columns or split it into two tables; do not create a technically valid but unreadable monster.

## Monsieur's delivery preference

Respond in concise French, with formal vouvoiement. Use tables when they improve comparison clarity, and keep URLs as plain text or inline code rather than hiding them behind Markdown link labels.

## Failure handling

- A raw pipe table appearing literally means the legacy route was used, not that Telegram Rich Messages are impossible.
- A successful Bot API response proves acceptance, not correct visual rendering.
- If Rich Messages are unavailable in the current adapter, state that limitation and provide the readable fallback.

## Official reference

The structured-format contract and object names are maintained in `references/telegram-bot-api-rich-messages.md`.
