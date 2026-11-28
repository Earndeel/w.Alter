## AWS "Resend code" Button — Shift+Mousedown Pattern

**Symptom**: Clicking the "Resend code" button on AWS sign-in verification page via JS `.click()` appears to succeed (no error, button not disabled) but the user doesn't receive a new email. Button text doesn't change to a countdown.

**Root cause**: AWS's React SPA uses a custom event handler that doesn't respond to synthetic `.click()` events. The button's click handler may be bound to a parent container via event delegation, or requires specific React synthetic event dispatching.

**What doesn't work**:
- `btn.click()` — button responds visually but no email sent
- `btn.dispatchEvent(new MouseEvent('click', {bubbles:true}))` — same result
- `btn.dispatchEvent(new PointerEvent('pointerdown', ...)) + pointerup + click` — same
- Clicking parent `<span>` or `<div>` — same

**What WORKS (confirmed 2026-06-11)**:
```javascript
btn.dispatchEvent(new MouseEvent("mousedown", {bubbles: true, shiftKey: true}));
btn.dispatchEvent(new MouseEvent("mouseup", {bubbles: true, shiftKey: true}));
btn.dispatchEvent(new MouseEvent("click", {bubbles: true}));
```
The `shiftKey: true` modifier is the key difference. AWS's React handler apparently checks for shift state to distinguish real clicks from synthetic ones. After dispatching with shift, the button shows a countdown and a new code is actually sent.

### Verification Code Timing

AWS verification codes expire in **~60 seconds**. The page shows a visible countdown timer. If the timer reaches 0, the code is dead.

### Fast MFA Flow Pattern (CRITICAL — every second counts)

1. Enter email → click Next
2. Enter password → click Sign in (use React setter for both)
3. **Before asking for code**: pre-navigate to the verification page, locate the input field, confirm the tab is alive
4. **Then** ask user for code (pre-warn: "le code expire en 60 secondes, envoyez-le moi vite")
5. Enter code via React setter → dispatch input+change events → click Verify
6. Total time budget: 60 seconds from code generation to Verify click
7. If expired: use shift+mousedown pattern above to resend, then ask user for the NEW code (old codes are invalidated)

### Pitfalls

- Each "Resend code" invalidates ALL previous codes. If the user sends code A, you resend, then user sends code B — code B is the only valid one. Don't mix codes.
- The round-trip from "user sends code in chat" → "agent enters code via Camoufox" takes ~15-20 seconds. Factor this into the 60-second budget.
- If the user takes >40 seconds to send the code, it's likely already expired by the time you enter it. Pre-warn them.
- Three consecutive expired codes = frustration. After 2 failures, switch strategy: use the shift+mousedown resend pattern and ask user to send the code IMMEDIATELY after receiving it.
