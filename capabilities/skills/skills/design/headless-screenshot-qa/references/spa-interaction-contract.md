# SPA landing interaction contract

Use this reference for a branded Vite/React landing page that links into an app surface and exposes media demos.

## Minimum browser matrix

Run the same contract at 1440×900 and 390×844. For each page collect `consoleErrors`, `pageErrors`, `failedRequests`, `scrollWidth`, and `clientWidth`.

| Surface | Required proof |
|---|---|
| `/` | landing heading renders; header `Student space` reaches `/app`; audio demo cards are present |
| `/` preview action | the in-page product preview reaches `/app` |
| `/` footer action | footer `Student space` reaches `/app` |
| `/app` | app shell renders on a fresh direct load |
| `/programs` | catalog renders and its navigation remains usable |

Pass conditions are no page/console errors, no failed local assets, and `scrollWidth === clientWidth` at both widths.

## Audio demo proof

Do not count a visible label as a working audio demo. Click one card and assert all three signals:

1. a request is made for the expected `/audio/cartesia/<asset>.wav` path;
2. the button enters its playing state and changes its accessible label;
3. the local file and deployed asset both return successfully.

Keep the phrase-to-asset map as the source of truth; do not invent filenames from transliteration.

## Route proof

Use exact URL assertions after clicks:

```js
await page.locator('header .marketing-login').click()
await page.waitForURL(/\\/app(?:\\?|$)/)
```

Repeat for any duplicate action in an ecosystem preview, mobile menu, or footer. A body-text assertion can pass while the browser is actually on `/undefined`, so it is not a substitute for the pathname check.

## Visual proof

Capture the affected section at the reported viewport. For responsive panel bugs, record the panel rectangle, computed horizontal padding, and child rectangles. A full-page screenshot is supplementary: use DOM geometry and per-viewport captures as the ground truth.

## Deployed SPA proof

After deployment, test both the immutable Pages deployment URL and the main project URL with a browser User-Agent and a cache-busting query. Verify `/`, direct `/app`, the audio asset, the route click, and the mobile overflow contract on both hosts.
