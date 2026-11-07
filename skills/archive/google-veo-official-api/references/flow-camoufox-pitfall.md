# Google Flow Web UI — Camoufox React Contenteditable Pitfall

When the Gemini API is not an option (e.g. Omni Flash 10s, no API key available), Google Flow's web UI must be automated via Camoufox. This document captures the key pitfall and workaround.

## The Problem

Google Flow uses React with `<div contenteditable="true" role="textbox">` for its prompt input (the "Que voulez-vous créer ?" field). Three failures compound:

1. **`/tab/type` times out** on Camoufox 9377 server — even for short text. The endpoint hangs (exit code 28).
2. **Setting `el.textContent` + `dispatchEvent('input')` does NOT update React state.** React's synthetic event system ignores DOM-level `textContent` mutations. The submit button clicks successfully but the app sees an empty field.
3. **`/tab/keyboard-type`** might work but is only available on the Max server (port 9378), not the base 9377.

## The Workaround

Use `/tab/evaluate` with `document.execCommand('insertText')` — one of the few DOM APIs that triggers React's native `beforeinput`/`input` events:

```javascript
var el = document.querySelector('[contenteditable="true"][role="textbox"]');
if (!el) return 'no element found';

// Focus the field
el.focus();

// Select existing placeholder text
document.execCommand('selectAll', false, null);

// Replace with the prompt via execCommand (triggers native input events React detects)
document.execCommand('insertText', false, 'your full prompt text here');

// Reinforce with explicit InputEvent for frameworks that need both
el.dispatchEvent(new InputEvent('input', {
    bubbles: true, cancelable: true,
    inputType: 'insertText'
}));
```

Confirmed working against Google Flow as of July 2026.

## Locating the Element

```javascript
// Primary: by contenteditable + role
var el = document.querySelector('[contenteditable="true"][role="textbox"]');

// Fallback: by placeholder text
var el = Array.from(document.querySelectorAll('[contenteditable]'))
    .find(e => e.textContent.includes('Que voulez-vous'));
```

## Submitting

Once the text is properly inserted and React has picked it up, click the submit button:

```javascript
// The submit button is typically the rightmost button in the bottom toolbar
var submit = Array.from(document.querySelectorAll('button')).find(function(b) {
    var r = b.getBoundingClientRect();
    var text = (b.textContent || '').trim();
    return r.y > 650 && text.includes('arrow_forward') && text.includes('Cr');
});
if (submit) submit.click();
```

Or use Camoufox snapshot to find the ref (typically around `e105`):

```bash
POST /tab/snapshot → find ref → POST /tab/click {ref: "e105"}
# If /tab/click times out (common on 9377), fall back to /tab/evaluate:
# submitBtn.click()
```

## Flow Configuration via JS

The generation panel (model, duration, aspect ratio, mode) can also be manipulated via `/tab/evaluate`:

```javascript
// Toggle mode: find tab buttons
var tabs = Array.from(document.querySelectorAll('[role="tab"]'));
var videoTab = tabs.find(t => t.textContent.includes('Vidéo'));
if (videoTab) videoTab.click();

// Select 9:16
var ratioTab = tabs.find(t => t.textContent.includes('9:16'));
if (ratioTab) ratioTab.click();
```

## Cookie Flow

Extract cookies from the user's Brave/Chrome profile on their Mac:

```bash
# On Mac via SSH:
sqlite3 ~/Library/Application\ Support/BraveSoftware/Brave-Browser/Default/Cookies \
  "SELECT host_key, name, encrypted_value FROM cookies WHERE host_key LIKE '%google%'"
```

Decrypt (macOS Keychain, Python):
```python
from Crypto.Cipher import AES
# macOS: security find-generic-password -wa 'Chrome Safe Storage'
# Linux: key is 'peanuts' (hardcoded in Chromium)
```

Then inject into Camoufox:
```bash
curl -X POST http://127.0.0.1:9377/tab/cookies \
  -d '{"userId":"...","tabId":"...","cookies":[...]}'
```

## Key Limitation

Flow's panel UI for model/duration configuration opens additional menus that may need separate click handling. Always screenshot+vision-analyze when the snapshot doesn't show the expected controls.

## Related

- `camoufox-automation` skill — general Camoufox SPA/React handling
- Main skill `google-veo-official-api` — prefer the API when available
