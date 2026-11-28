# Bedrock Use Case Form — Camoufox Automation

When Anthropic models return `ResourceNotFoundException: Model use case details have not been submitted`, you must submit the use case form via the AWS Console. This reference documents the full Camoufox browser automation flow.

## Prerequisites

- Camoufox-max server running (`/root/.hermes/camoufox-max/server-max.js`)
- AWS cookies injected (from Mac Brave via CDP extraction)
- Tailscale exit node active (Mac SOCKS5 proxy on `100.127.150.1:1080`)

## Flow

### 1. Navigate to Model Catalog

```
POST /session { "url": "https://us-east-1.console.aws.amazon.com/bedrock/home?region=«secret:vault»#/modelcatalog" }
```

The old `#/modelaccess` URL redirects to catalog now.

### 2. Find the Yellow Banner

The page shows: *"Anthropic requires first-time customers to submit use case details before invoking a model."*

There is a **"Submit use case details"** button on the banner AND one inside each Anthropic model card. Either works.

### 3. Click "Submit use case details"

```javascript
// Via /tab/evaluate
Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Submit use case details')).click();
```

### 4. Fill the Form

The form has these fields:

| Field | Type | Recommended Value |
|-------|------|-------------------|
| Company name | text input | (user's company) |
| Company website URL | text input | (user's site) |
| Industry | AWS custom dropdown (listbox) | "Software as a Service" |
| Intended users | checkboxes: `internal` + `external` | Check `internal` |
| Use case description | textarea (500 char max) | (describe the use case) |

**AWS custom dropdown interaction** — these are NOT native `<select>`. They use:
- `aria-haspopup="listbox"` on the trigger button
- `aria-expanded="true/false"` to track state
- Options rendered as `[role="option"]` inside a `[role="listbox"]`

**Opening the dropdown:**
```javascript
const btn = Array.from(document.querySelectorAll('button'))
    .find(b => b.textContent.includes('Choose an option'));
// Dispatch real mouse events (click() sometimes doesn't work)
btn.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
btn.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
btn.dispatchEvent(new MouseEvent('click', {bubbles:true}));
// Verify: btn.getAttribute('aria-expanded') === 'true'
```

**Selecting an option:**
```javascript
const opt = Array.from(document.querySelectorAll('[role="option"]'))
    .find(o => o.textContent.includes('Software as a Service'));
// Need coordinates for reliable click
const rect = opt.getBoundingClientRect();
const x = rect.x + rect.width/2, y = rect.y + rect.height/2;
['mousedown','mouseup','click'].forEach(type => {
    opt.dispatchEvent(new MouseEvent(type, {bubbles:true, clientX:x, clientY:y}));
});
```

### 5. Submit

```javascript
Array.from(document.querySelectorAll('button'))
    .find(b => b.textContent.trim() === 'Submit').click();
```

### 6. Verify

Green banner: *"Use case details for Anthropic submitted successfully"*

## Pitfalls

- **React inputs** — `.value =` doesn't trigger onChange. Use `nativeInputValueSetter` + `dispatchEvent(new Event('input', {bubbles:true}))`.
- **Dropdown needs real mouse events** — `element.click()` sometimes fails to open AWS custom dropdowns. Use `dispatchEvent` with `mousedown` → `mouseup` → `click` sequence.
- **Multiple dialogs** — AWS console stacks dialogs. The EULA Accept/Decline/Customize dialog may appear behind the form. Close it first if blocking.
- **Page scroll position** — After filling the form, scroll to the Submit button. The modal content may be taller than viewport.
- **Form closes on submit** — The modal dismisses and the page refreshes. Check for the green success banner on the main page.
