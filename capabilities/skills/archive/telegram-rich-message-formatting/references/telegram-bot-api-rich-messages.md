# Telegram Bot API Rich Messages — reference

Official documentation:

```text
https://core.telegram.org/bots/api#rich-message-formatting-options
```

The current Bot API documentation defines structured rich-message types including:

- `RichMessage`
- `InputRichMessage`
- `RichBlock`
- `RichBlockTable`
- `RichBlockTableCell`
- `sendRichMessage`
- `sendRichMessageDraft`

It also exposes structured blocks for paragraphs, headings, preformatted text, lists, quotations, dividers, details, maps, media, and other content.

## Operational interpretation

- Markdown pipe syntax is only text unless the Hermes adapter parses it into a rich-message table.
- `parse_mode=MarkdownV2` and `parse_mode=HTML` are legacy formatting paths; they do not by themselves create a `RichBlockTable`.
- `telegram.extra.rich_messages: true` is the relevant Hermes configuration signal, but rendering must still be verified in the actual outgoing Telegram message.
- A successful API response confirms transport acceptance, not visual table rendering.

## Test fixture

Use a narrow table for validation:

| Model | Cost / s | Cost / 10 s |
|---|---:|---:|
| Test A | $0.01 | $0.10 |
| Test B | $0.02 | $0.20 |

If the user sees literal pipes and dashes, the legacy route was used or conversion did not occur. Use HTML or a preformatted aligned fallback only when the Rich Message route is unavailable.
