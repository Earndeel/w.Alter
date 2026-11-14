# web-service-browser — Sending results and images to Telegram, image analysis, the dating-profile analysis workflow.

Moved verbatim from SKILL.md on 2026-11-01.

## Telegram Delivery

Send screenshots and data to Telegram via curl. **Critical syntax**: use `$(vault get ...)` inline, NOT `$(vault get ...)` in a variable assignment with `)` — bash misparses the closing paren.

**See**: `references/bumble-cookie-auth.md` for Bumble-specific cookie details, Camoufox failure, and Brave-in-webtop workaround.

**See `references/telegram-formatting.md` for full formatting rules.**

Key rules:
- **NEVER send as document/file** — user wants to READ in Telegram, not download
- **NEVER reformulate** service responses — send EXACT text from Gemini/Grok/etc
- **Single message, 4096 char max** — trim content to fit, don't split
- **HTML format** (`parse_mode=HTML`), NOT Markdown — HTML renders properly with bold, italic, etc.
- Use `<b>bold</b>` for headers, `━━━` separators, `▸` bullets. NO tables (convert to lists). NO `#headers`.

```bash
# CORRECT
curl -s -X POST "https://api.telegram.org/bot$(vault get telegram/bot_token 2>/dev/null)/sendPhoto" \
  -F "chat_id=1146774717" -F "photo=@/tmp/screenshot.png" -F "caption=Description"

# WRONG — syntax error
BOT_TOKEN=*** get telegram/bot_token 2>/dev/null)
```

For long captions, use `-F "text=..."` with `sendMessage` instead of `sendPhoto`.

## Image Analysis Integration

Many X posts convey critical info via images (benchmarks, diagrams, screenshots). After scraping:
1. `GET /tabs/:id/images` → extract image URLs
2. `vision_analyze` on each image
3. Fuse text + image analysis for complete understanding

Images are lazy-loaded. Scroll first, then call `/images` endpoint. Filter out profile pics (`width < 100` or `profile_images` in URL).

## Sending to Telegram

**Format**: `parse_mode=HTML` (not Markdown). Telegram does NOT support `<table>` tags.
**Limit**: 4096 chars per message. Split if needed.
**Rule**: Send EXACT response from service, never reformat. No screenshots/files unless user asks.

**User frustration signals** (from session corrections):
- "je t'ai pas demandé un screenshot" — don't add screenshots without request
- "c'est pas la réponse exacte" — send raw text, not summaries
- "je veux simplement ouvrir mon message Telegram et avoir un message propre" — user wants to READ in Telegram, not download files

## Dating Profile Analysis Workflow

When analyzing a dating profile (Bumble, Tinder, etc.), follow this sequence:

1. **Identify the correct conversation** — Do NOT assume the top sidebar entry is the most recent incoming message. "Your move" means they messaged last, but verify timestamps by clicking into each conversation. Compare timestamps to find the actual most recent incoming message.
2. **Extract ALL profile text** — bio, prompts, basics (height, education, smoking, etc.), location, Spotify artists.
3. **Download and analyze EVERY profile photo** — this is NOT optional. The user expects OSINT + psychological analysis of the visual content. Use `vision_analyze` on each photo. Extract:
   - Apparence physique, style vestimentaire
   - Lieu/décor (OSINT géographique)
   - Langage corporel, expression faciale
   - Marques visibles (luxe, voitures, accessoires)
   - Signaux socio-économiques
   - Intention psychologique derrière la photo
   - Cohérence entre les photos (cheveux différents = époques différentes ?)
4. **Check social media** — if IG handle in bio, check the profile (followers, posts, private/public).
5. **Compile full synthesis** — psychological profile, risk/interest assessment, conversation strategy.

**Bumble conversation click selector** (tested 2026-06-02):
```javascript
// CORRECT — click the .contact div, not just the name text
document.querySelectorAll('.contact').forEach(c => {
    if (c.querySelector('.contact__name-text')?.textContent.trim() === 'NameHere') c.click();
});
```
Do NOT use `page.get_by_text("Name")` — it hits the container div which intercepts clicks. Use the JS evaluate approach above with `page.mouse.click(coords)` on the `.contact__name-text` element's bounding box center.

## Sending to Telegram

```bash
# Photo
curl -s -X POST "https://api.telegram.org/bot$(vault get telegram/bot_token)/sendPhoto" \
  -F "chat_id=1146774717" -F "photo=@/tmp/image.png" -F "caption=Description"

# Document (JSON, text files)
curl -s -X POST "https://api.telegram.org/bot$(vault get telegram/bot_token)/sendDocument" \
  -F "chat_id=1146774717" -F "document=@/tmp/data.json" -F "caption=Data file"

# Text message
curl -s -X POST "https://api.telegram.org/bot$(vault get telegram/bot_token)/sendMessage" \
  -F "chat_id=1146774717" -F "text=Multi-line message here"
```

**Pitfall**: Use `$(vault get ...)` NOT `$(vault get ... 2>/dev/null)` — the `)` after redirection causes bash syntax errors in some contexts.

