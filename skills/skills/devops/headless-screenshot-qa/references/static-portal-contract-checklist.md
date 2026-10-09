# Static portal contract checklist

Use this reference when a redesign targets an existing static multi-page portal. It records the behavior surface that must survive a visual rewrite; it is not a substitute for reading the current source.

## Audit before editing

For each route, record:

- file and clean URL alias (`/`, `/login`, `/dashboard`, `/interface`, etc.);
- public vs authenticated boundary;
- critical DOM IDs used by inline JavaScript;
- form fields, submit handlers, OAuth links, and session restore calls;
- `fetch`, `EventSource`, upload, polling, and callback endpoints;
- local/session storage keys and post-login redirects;
- payment plan names, custom minimums, and checkout payload shape;
- links to other app surfaces and required legacy entrypoints;
- existing tests that read the artifact as a behavior contract.

Use `search_files` to locate symbols/endpoints and `read_file` to inspect their definitions before changing markup. Do not infer contracts from visual appearance.

## Scena example from the July 2026 portal rewrite

These were contracts verified during the redesign and should be rechecked if the Scena portal is edited again:

| Surface | Contract to preserve |
|---|---|
| Public entrypoints | `index.html`, `studio.html`, `connect.html`, `pricing.html`, `docs.html`, `contact.html` |
| Client auth | Google OAuth plus email sign-in/sign-up; session check at `/api/auth/get-session` |
| Client checkout | `/api/client/checkout` with `usd19`, `usd49`, and `custom`; custom credits minimum is 50 |
| App surfaces | `dashboard.html` and `interface.html` retain their own authenticated workflows |
| Operator navigation | Admin entrypoint keeps a discoverable link to `operator.html` |
| Public assets | Generated media lives under `pages/portal/assets/media/`; every image has meaningful `alt` text |

The plan names and minimum are business behavior, not copy. Keep them in the checkout handler and verify them with the existing tests; do not silently translate or rename them during a visual refresh.

## Visual/static regression matrix

Serve the exact portal directory with `terminal(background=true)` and visit every public route at 1440px and 390px widths using Playwright. For every visit collect:

```js
{
  httpStatus,
  scrollWidth,
  clientWidth,
  scrollHeight,
  consoleErrors,
  pageErrors,
  failedRequests,
  hiddenRevealCount
}
```

The pass conditions are:

- `httpStatus === 200`;
- `scrollWidth === clientWidth` at both widths;
- no console/page errors and no failed local asset requests on public pages;
- `hiddenRevealCount === 0` after the capture wait or deterministic reveal step;
- no duplicate IDs, missing image `alt`, or unlabeled interactive controls;
- targeted contract tests remain green.

A protected page may legitimately attempt an API call that is unavailable from a localhost origin. Report that separately as an environment/CORS limitation; do not confuse it with a public-page asset or JavaScript regression.

## Fix patterns

- **Horizontal overflow:** inspect transformed ancestors first. Marquees and rotated full-width bands can expand document geometry even when their child is clipped. Prefer `html { overflow-x: clip; }`, a contained ticker, and no outer rotation on small screens.
- **Blank full-page sections:** do not trust a giant screenshot until the DOM reports non-zero section heights and children. Make reveal states deterministic for screenshots or force them visible in the QA harness.
- **Unreadable colored-band buttons:** explicitly set button text color when a parent section changes `color`; inheritance can produce white-on-white labels.
- **Cut oversized display text:** measure each mobile heading's `scrollWidth` against its container and reduce the mobile font clamp before delivery.
- **Secrets in snippets:** use a visibly fake placeholder such as `sk_scena_demo` only in documentation-style sample code; never copy a real provider key into a static file.
