# Telegram Message Formatting

Monsieur veut des messages propres directement dans Telegram — pas de fichiers à télécharger.

## Rules

1. **NEVER send as document/file** unless explicitly asked. User opens Telegram to READ, not to download.
2. **NEVER reformulate/summarize** a service's response. Send the EXACT text from Gemini/Grok/etc.
3. **Single message preferred.** Telegram limit = 4096 chars. Trim content to fit, don't split unless >4096.
4. **Use HTML format** (`parse_mode=HTML`), NOT Markdown — HTML renders properly with bold, italic, etc.
5. **NO tables** — Telegram doesn't support `<table>` tags. Convert to formatted lists.

## HTML Formatting (PREFERRED)

```python
import subprocess
bot = subprocess.run(['vault', 'get', 'telegram/bot_token'], capture_output=True, text=True).stdout.strip()
result = subprocess.run([
    'curl', '-s', '-X', 'POST',
    f'https://api.telegram.org/bot{bot}/sendMessage',
    '-F', 'chat_id=1146774717',
    '-F', f'text={html_text}',
    '-F', 'parse_mode=HTML'
], capture_output=True, text=True)
```

## Telegram HTML Compatibility

| Feature | Telegram Support | Syntax |
|---------|-----------------|--------|
| **Bold** | ✅ | `<b>text</b>` or `<strong>text</strong>` |
| *Italic* | ✅ | `<em>text</em>` or `<i>text</i>` |
| `Code` | ✅ | `<code>text</code>` |
| ```Code block``` | ✅ | `<pre>text</pre>` |
| Links | ✅ | `<a href="url">text</a>` |
| Strikethrough | ✅ | `<s>text</s>` or `<strike>text</strike>` |
| Underline | ✅ | `<u>text</u>` or `<ins>text</ins>` |
| #headings | ❌ | Use `<b>HEADING</b>` |
| Tables | ❌ | Convert to formatted lists |
| Max length | 4096 chars | Trim to fit |

## Formatting Template (HTML)

```html
🧠 <b>TITRE PRINCIPAL</b>
<em>sous-titre/contexte</em>

━━━
<b>1. SECTION ONE</b>
Description text ici.

<b>▸ Sous-point :</b> explication
<b>▸ Sous-point :</b> explication

━━━
<b>2. SECTION TWO</b>
```

## Converting Tables to Lists

Tables are NOT supported. Convert:

**Before (table):**
```
| Modèle | Mise à jour | Impact |
|---|---|---|
| Opus 4.8 | "Saut cybernétique" | Raisonnement radical |
```

**After (formatted list):**
```html
<b>Opus 4.8</b> — "Saut cybernétique" (Pliny)
→ Raisonnement radical

<b>OpenClaw 2026.5.28</b> — +16% perf
→ Support direct d'Opus 4.8
```

## Pitfalls

- HTML tags must be properly closed — unclosed `<b>` breaks the message
- Telegram rejects unsupported HTML tags (e.g., `<table>`, `<div>`, `<span>`)
- If message > 4096 chars, trim content (remove verbose sentences) rather than splitting
- `sendPhoto` caption also has 1024 char limit — use `sendMessage` for long text
- User wants to OPEN Telegram and SEE the message — not download a file
- **NEVER send Markdown** — it doesn't render properly (no bold visible, raw asterisks shown)
- Use `━━━` as section separators, `▸` for sub-items
- **NEVER send screenshots unless user explicitly asks** — user was frustrated when screenshots were added without request
- **NEVER reformulate/reformat** a service's response — send EXACT text from Gemini/Grok/etc
- **NEVER send as document/file** — user wants to read directly in Telegram, not download
- **If user asks for "exact response"**, send the raw text with HTML formatting, not a summary
- **User correction pattern**: "je t'ai pas demandé un screenshot", "c'est pas la réponse exacte", "je veux simplement ouvrir mon message Telegram et avoir un message propre"
