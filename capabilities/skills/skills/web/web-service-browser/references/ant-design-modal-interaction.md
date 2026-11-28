# Ant Design Modal Interaction — Hidden from Accessibility Tree

## Problem

Ant Design (`ant-design`) modals render via React portals at `document.body` level. They are **visible on screen** (screenshot confirms) but **invisible to the accessibility tree** (snapshot returns no elements). The `evaluate` endpoint also struggles — `querySelectorAll('*')` with `innerText` checks returns empty even though `document.body.innerText` contains the modal text.

## Diagnosis

If screenshot shows a modal but snapshot returns nothing for its elements:

```javascript
// 1. Confirm modal text exists in body
document.body.innerText.indexOf('Your Modal Text') // > -1 = it's there

// 2. Find the container
var all = document.querySelectorAll('div.ant-modal-content');
for (var d of all) {
    if (d.innerHTML.includes('Your Modal Text')) {
        var rect = d.getBoundingClientRect();
        // rect.width > 0 && rect.height > 0 = visible and interactable
    }
}
```

## Clicking Hidden Modal Elements

Standard `click()` API calls on snapshot refs don't work because the modal isn't in the accessibility tree. Use **coordinate-based mouse events**:

```javascript
// Step 1: Find element via TreeWalker (works when querySelector fails)
var found = [];
function walk(node) {
    if (node.nodeType === 3) { // text node
        var t = node.textContent.trim();
        if (t === 'Target Text') {
            var p = node.parentElement;
            var rect = p.getBoundingClientRect();
            found.push({
                text: t, tag: p.tagName,
                x: Math.round(rect.x + rect.width/2),
                y: Math.round(rect.y + rect.height/2),
                w: Math.round(rect.width), h: Math.round(rect.height)
            });
        }
    }
    for (var c of node.childNodes) walk(c);
}
walk(document.body);
// found[0].x, found[0].y = center coordinates

// Step 2: Dispatch full mouse event sequence at coordinates
var el = document.elementFromPoint(found[0].x, found[0].y);
el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window, clientX: found[0].x, clientY: found[0].y}));
el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window, clientX: found[0].x, clientY: found[0].y}));
el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window, clientX: found[0].x, clientY: found[0].y}));
```

## Overlay Detection

Sometimes `document.elementFromPoint(x, y)` returns a different element than expected (z-index stacking). Check what's actually at the target coordinates:

```javascript
var target = document.elementFromPoint(x, y);
// If target.tagName !== expected, there's an overlay
// Common: ant-modal-wrap with z-index 9999 covering other modals
// Fix: close the overlay modal first (find its close button or press Escape)
```

## Multiple Modals (Stacking)

Ant Design can stack multiple modals. Each `ant-modal-wrap` has `z-index: 9999`. When a retention/discount modal appears AFTER a cancellation modal:

1. The second modal overlays the first
2. `elementFromPoint` returns the top modal's elements
3. Process modals in order — close/complete the top one first

## Common Subscription Cancellation Flow

Many SaaS services (Hailuo, etc.) use a multi-step cancellation pattern:

1. **Click "Cancel Plan"** → opens reason selection modal
2. **Select reason** (Low usage, Price too high, etc.) → click radio/card
3. **Click "Continue to cancel"** → opens retention offer modal
4. **Dismiss retention offer** → click "Cancel Subscription" (NOT "Claim Discount")
5. **Final confirmation** → may require one more click

Each step may use Ant Design modals with the portal rendering issue above.

## Verified on

- hailuoai.video (June 2026) — Standard Plan cancellation with 6 reason options + 15% retention offer
