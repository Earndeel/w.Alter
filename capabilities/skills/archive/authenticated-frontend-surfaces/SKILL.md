---
name: authenticated-frontend-surfaces
description: Use when redesigning authenticated frontend surfaces.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [frontend, authenticated, dashboard, studio, accessibility, visual-qa]
    category: software-development
    related_skills: [headless-screenshot-qa, cloudflare-pages-deploy]
---

# Authenticated Frontend Surfaces Skill

Redesign and verify login, dashboard, Studio, and other authenticated frontend surfaces without breaking their DOM contracts or API flows. This skill is for static or mixed HTML/CSS/JS products where legacy page-local styles, shared stylesheets, and authenticated initialization can collide. It does not redesign backend auth, change provider APIs, or replace the product’s existing application architecture.

## When to Use

- Login text or controls are invisible, low-contrast, or unreadable.
- Dashboard and Studio pages look like unrelated products.
- Rounded cards are mixed with zero-radius frames, hard offset shadows, or square controls without a deliberate art direction.
- A shared CSS refactor is layered over old inline `<style>` blocks or dark custom-property tokens.
- A visual redesign must preserve form IDs, session checks, generation payloads, checkout links, or route aliases.
- Authenticated pages cannot be reviewed through an ordinary unauthenticated browser visit.

Do not use this skill for a pure backend auth/API change, a marketing-only landing page, or a one-off screenshot with no code change. Use the project’s security or backend workflow for credential and tenancy changes.

## Prerequisites

- Read repository instructions and identify the frontend root.
- Use `search_files` and `read_file` to locate page bodies, IDs, inline styles, shared CSS, initialization code, and tests before editing.
- Use `patch` for existing-file edits; keep DOM and JavaScript contracts intact unless the request explicitly includes behavior changes.
- Use `terminal` with the project’s own test runner and a real browser/Playwright smoke harness when the page is static or server-rendered.
- Have a local route or preview artifact available before a production design deploy.
- Keep credentials, cookies, API keys, and user data out of screenshots, fixtures, logs, and skill references.

## How to Run

1. Load this skill together with `headless-screenshot-qa` for screenshot mechanics and `cloudflare-pages-deploy` when a Pages deployment is involved.
2. Audit the cascade and behavior contract before writing CSS.
3. Reproduce the visible state locally or against a safe preview, using mocked session/API responses where authentication is required.
4. Establish scoped product tokens and one geometry contract for the authenticated surface.
5. Verify computed contrast, responsive layout, console output, DOM interactions, and payload preservation.
6. Capture desktop/mobile evidence and obtain a visual review before production deployment.

Completion means the affected surface is exercised in its authenticated state, its critical interactions still work, the responsive and contrast checks pass, and every production-facing visual change has a reviewable preview or screenshot.

## Quick Reference

| Concern | Default contract |
|---|---|
| Surface scope | Body classes such as `auth-page`, `dashboard-page`, `studio-page` |
| Workspace containers | Consistent rounded surfaces, usually 18–24px radius |
| Controls | Consistent 10–14px radius; no accidental zero-radius inheritance |
| Status/navigation | Pills are reserved for status, credits, tabs, or compact navigation |
| Primary actions | Compute contrast; use dark ink on a bright accent when white fails |
| Borders | Quiet tokenized borders; avoid black rectangular frames inside rounded shells |
| Shadows | Soft elevation for product surfaces; no accidental offset blocks |
| QA states | Anonymous login, authenticated dashboard, initialized Studio, generation in-flight |
| Layout check | `document.documentElement.scrollWidth === document.documentElement.clientWidth` |
| Production gate | Local/preview visual review before deploy; direct deploy only after explicit approval |

## Procedure

### 1. Map the behavior and cascade

Trace the actual page rather than inferring its shape.

- Locate the `<body>` class, page-local `<style>` blocks, shared stylesheet links, and the final CSS load order.
- Locate every critical ID and class used by JavaScript: auth forms, session checks, dashboard data targets, Studio inputs, preprompt containers, generation buttons, output tiles, and status indicators.
- Locate all fetch/EventSource endpoints and route redirects. Record which responses cause an anonymous page to redirect and which responses initialize authenticated UI.
- Read the neighboring tests. Treat expected IDs, route aliases, title/branding strings, and payload keys as contracts unless the request explicitly changes them.

**Done when:** you can name the style source that controls each visible problem and can list the DOM/API contracts that must remain unchanged.

### 2. Reproduce the real visual state

Do not judge only the unauthenticated shell.

- Visit login anonymously.
- For dashboard and Studio, intercept session/profile/sync calls in the browser harness and return safe fixture data so the authenticated DOM renders.
- Wait for initialization code to finish before measuring or capturing. Dynamic preprompt lists and data cards may not exist at first paint.
- Capture at least one desktop and one narrow mobile viewport for every affected surface.

**Done when:** screenshots show the same post-auth components that the user reports, not a redirect or an empty loading shell.

### 3. Establish scoped tokens

Give each authenticated surface an explicit token set rather than depending on landing-page globals or partially surviving legacy variables. At minimum define background, secondary background, panel, panel-secondary, ink, muted text, soft text, border, strong border, accent, success, warning, danger, and focus colors.

Use a body scope so an old `:root` remains harmless:

```css
body.studio-page {
  --bg: #ece7dc;
  --bg2: #f5f0e7;
  --panel: #fffdf8;
  --panel2: #eee8dc;
  --text: #101010;
  --muted: #625c53;
  --line: rgba(16, 16, 16, .16);
  --line2: rgba(16, 16, 16, .28);
  --accent: #ff3b18;
  background: var(--bg);
  color: var(--text);
}
```

Repeat the complete set for login and dashboard when their legacy page-local tokens differ. Do not assume that a later shared stylesheet overrides every declaration from an earlier inline block: it only wins where it redeclares the property with sufficient specificity.

**Done when:** every authenticated surface resolves its foregrounds, backgrounds, borders, and radii from an intentional scoped token set.

### 4. Apply a geometry contract

Use semantic geometry instead of making every element independently rounded.

- Workspace shells and major panels: 18–24px.
- Inputs, buttons, tab groups, and compact controls: 10–14px.
- Pills: statuses, credits, workflow chips, and compact navigation only.
- Drop zones: rounded dashed containers, not square frames inside rounded cards.
- Remove accidental `border-radius: 0`, black offset shadows, and heavy rectangular borders from authenticated product surfaces unless the art direction explicitly calls for them.
- Keep the landing page’s editorial hard-edge language separate from the authenticated workspace language when the two serve different jobs.

**Done when:** a screenshot shows a deliberate hierarchy of shells, controls, and pills with no unexplained square/rounded collision.

### 5. Verify contrast numerically

Vision is a second opinion for hierarchy, not the contrast oracle. Extract `getComputedStyle(element).color` and `backgroundColor` through Playwright or the browser console, resolve transparent backgrounds against the nearest real surface, and calculate relative luminance.

Use these thresholds:

- Normal text: at least 4.5:1.
- Large text: at least 3:1.
- UI labels and control text: target at least 4.5:1 when practical.

Bright vermillon accents commonly fail with white text. Prefer dark ink or a darker accent after measurement; never preserve an invisible label for palette purity. Check placeholders, muted descriptions, inactive tabs, status chips, and Google/OAuth labels separately.

**Done when:** critical text/control pairs have measured ratios recorded in the QA output, not merely a favorable visual impression.

### 6. Preserve behavior while styling

Prefer CSS and scoped body classes before changing markup. If a body class is needed to isolate a product surface, add only that class and preserve all existing IDs, handlers, links, form fields, and endpoint strings.

When editing large HTML, do not copy line-numbered `read_file` output back into the file. Use a targeted `patch`; re-read the exact region if a patch is ambiguous. Do not remove legacy JavaScript just because the visual layer is being replaced.

**Done when:** the DOM contract tests remain green and the diff contains no unrelated auth, billing, provider, or routing changes.

### 7. Test authenticated interactions with fixtures

Use safe browser fixtures, never real provider calls.

- Anonymous login fixture: session endpoint returns no user, allowing tab switching and form validation to be tested.
- Authenticated fixture: session/profile/sync endpoints return a minimal safe user and empty or deterministic data.
- Studio generation fixture: intercept the pipeline POST, record its JSON body, return a deterministic job ID, and stub stream/poll behavior.
- Exercise login tab switching, preprompt expansion, payload preview, generate/reset states, and dashboard card rendering.

Keep fixture responses minimal and avoid credentials. A session fixture that returns a user on the login page will legitimately trigger redirect and make login interaction tests appear to fail.

**Done when:** the browser harness proves both anonymous and authenticated paths and captures the expected generation payload without contacting a paid service.

### 8. Run responsive and visual QA

For every affected route and at desktop/mobile widths:

- Assert HTTP success and no horizontal overflow.
- Collect console errors, page errors, failed asset requests, and unexpected redirects.
- Assert critical elements are visible after initialization.
- Capture screenshots of the actual post-auth state.
- Inspect the screenshots for hierarchy, text visibility, geometry collisions, and mobile stacking.

Cross-check vision against DOM measurements. A vision model can miss or misread content in tall screenshots; a non-zero DOM rect and computed style are stronger evidence for presence and contrast.

**Done when:** the route matrix is green and screenshots contain no blocking visual defect.

### 9. Review before production

Deploy a preview only when credentials and project selection are verified. Otherwise keep the local artifact and screenshots as the review checkpoint. Do not deploy a public redesign directly to production merely because unit tests pass. After approval, deploy to the confirmed Pages project, verify the new deployment hash and custom domain, fetch the served HTML/CSS, and account for CDN/browser caching with a versioned asset query or equivalent cache strategy.

**Done when:** the reviewer has seen the final visual state and the deployed bytes, not just a successful Wrangler exit code.

## Provider-backed phrase audio in a static SPA

For dashboards that teach or review spoken phrases, keep provider credentials out of the browser. On a static deployment, generate the finite phrase library at build time from a vault-backed credential, map exact source strings to public audio assets, and use one shared player across Overview, Practice, and Phrasebook. Resolve voice metadata before generation when locale or gender matters; expose the provider/voice in accessible UI state, stop the previous clip before starting another, and keep browser speech only as an explicit fallback for missing or failed assets. Verify real audio requests and decoded files in addition to visual and DOM checks. The reusable Cartesia/React pattern is documented in `references/provider-backed-spa-audio.md`.

## Pitfalls

1. **Partial override of a legacy dark theme.** A shared stylesheet changes `background` but not an old inline `color: var(--text)`, leaving white text on white surfaces. Trace declarations and redeclare the full scoped token set.
2. **Vision-only contrast iteration.** A model may call a mathematically accessible dark surface unreadable or miss a bright-accent failure. Measure computed colors and luminance before changing the palette.
3. **Square parent, rounded child.** Zero-radius page-local rules and black offset shadows often survive a redesign. Define the geometry contract at the body scope and override every major shell/control selector.
4. **Testing the redirect instead of the application.** Dashboard/Studio tests that do not mock session responses only validate the login redirect. Fixture the session and data endpoints first.
5. **Authenticated fixture on login.** Returning a user from the login session check is correct application behavior but prevents testing login tabs. Use an explicit anonymous fixture for login.
6. **Dynamic content measured too early.** Preprompt lists, workflow chips, and dashboard data can be inserted asynchronously. Wait for initialization and assert element counts before screenshotting.
7. **Payload drift during visual refactor.** Do not rename IDs, form fields, provider values, or payload keys while changing CSS. Run the existing contract tests and capture the outgoing JSON.
8. **Unreviewed production styling.** A passing test suite does not replace a visual checkpoint. Keep production unchanged until the user reviews a local/preview capture, unless the user explicitly authorizes the production deploy.
9. **Cache mistaken for a failed redesign.** After deploy, verify the served CSS/HTML bytes and use an asset query/version or a deliberate cache strategy before diagnosing the visual result as stale code.

## Verification

- [ ] Critical page IDs, links, endpoint strings, and payload keys were traced before editing.
- [ ] Login was tested with an anonymous session fixture.
- [ ] Dashboard and Studio were tested with authenticated fixtures.
- [ ] CSS load order and legacy custom-property collisions were checked.
- [ ] Foreground/background pairs were measured from computed styles.
- [ ] Primary text meets 4.5:1 where normal-sized; large text meets 3:1.
- [ ] Workspace shells, controls, and status pills follow one geometry contract.
- [ ] Desktop and mobile screenshots show no unexplained square/rounded collision.
- [ ] `scrollWidth === clientWidth` at every tested viewport.
- [ ] No console/page errors or failed critical assets remain.
- [ ] Generation/reset and login tab interactions were exercised without paid API calls.
- [ ] Relevant project tests pass.
- [ ] Production was not changed before visual review and explicit approval.

## References

- `references/authenticated-surface-qa.md` — Cascade diagnosis, contrast examples, fixture matrix, and reusable checks from the Scena workspace review.
- Pair with `headless-screenshot-qa` for screenshot slicing and DOM measurement details.
- Pair with `cloudflare-pages-deploy` for Pages project verification, cache handling, and deployment checks.
