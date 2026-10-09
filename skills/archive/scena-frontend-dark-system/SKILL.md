---
name: scena-frontend-dark-system
description: Dark visual system for Scena multi-page surfaces.
version: 1.0.0
author: "Lucas Jouvençon; Hermes Agent"
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [scena, frontend, dashboard, landing, dark-theme, visual-qa]
    category: software-development
    related_skills: [authenticated-frontend-surfaces, headless-screenshot-qa]
---

# Scena Frontend Dark System Skill

This skill defines a reusable visual method for Scena’s public pages, authentication, client dashboard, Studio, and operator admin. It unifies their palette and geometry while preserving existing DOM, auth, API, billing, and routing contracts. It is a design and verification method, not a backend security or cloud-resource procedure.

## When to Use

- A Scena request spans multiple HTML routes or asks for one visual language.
- Landing, login, dashboard, Studio, and admin pages have drifted into unrelated themes.
- A shared stylesheet is loaded after page-local styles and unexpectedly overrides tokens.
- An authenticated surface needs fixture-backed browser QA rather than a redirect screenshot.
- A dark redesign needs numeric contrast and responsive evidence before review.

## Prerequisites

- Locate the static portal roots with `search_files` and inspect them with `read_file`.
- Identify shared stylesheets, page-local `<style>` blocks, body classes, critical IDs, API paths, route links, and neighboring tests before editing.
- Load `authenticated-frontend-surfaces` and `headless-screenshot-qa` when available.
- Keep real credentials, cookies, account data, and provider responses out of fixtures and screenshots.

## How to Run

1. Map the route and CSS cascade.
2. Establish the shared dark tokens and scoped authenticated/admin tokens.
3. Override explicit legacy light declarations and dark-on-dark descendants.
4. Preserve DOM and API contracts while changing style.
5. Serve the exact source with `terminal` and run fixture-backed Playwright checks.
6. Measure contrast and overflow; inspect desktop and mobile screenshots.
7. Present a preview before any production release.

## Quick Reference

| Surface | CSS scope | Evidence state |
|---|---|---|
| Public pages | `body[data-page-shell]` | anonymous landing at desktop/mobile |
| Login | `body.auth-page` | anonymous email/Google auth form |
| Client dashboard | `body.dashboard-page` | synthetic session, jobs, bot status |
| Studio/interface | `body.studio-page` | synthetic session and composer |
| Admin | `body.admin-dashboard` | synthetic admin token and overview |

Dark starting tokens:

```css
:root {
  color-scheme: dark;
  --paper: #07090d;
  --paper-2: #0d1117;
  --ink: #f4f2ea;
  --muted: #969da6;
  --line: rgba(255, 255, 255, .10);
  --line-strong: rgba(255, 255, 255, .20);
  --panel: #11151c;
  --panel-2: #181e27;
  --accent: #ff5a36;
  --accent-soft: #ff9b82;
  --success: #54d993;
}
```

Use dark ink on bright coral or lime controls. Measure any exception instead of trusting visual intuition.

## Procedure

### 1. Map the cascade and behavior surface

Create a route table containing every production HTML file, shared stylesheet usage, page-local style usage, body class, clean/extensionful links, and critical JavaScript IDs. Trace the actual style order: a shared stylesheet linked after an inline block can replace page-local `:root` variables.

Search for explicit light declarations (`#fff`, `white`, paper backgrounds, light accent panels) and old descendants such as `.dark-section .section-title { color: var(--white) }`. When a token is repurposed as a dark panel, these descendants can become nearly black and must be overridden explicitly.

Record auth/session keys, dashboard profile/jobs/sync/bot calls, Studio payload controls, and admin navigation/modal IDs. A visual change must not rename these contracts.

### 2. Apply one dark language

Patch the shared stylesheet with the complete dark token set, `color-scheme: dark`, page background, surfaces, borders, muted text, focus color, accents, and status colors. A final canonical override block is acceptable when legacy selectors are numerous; it avoids an unsafe rewrite of unrelated behavior.

Scope authenticated differences with `body.auth-page`, `body.dashboard-page`, and `body.studio-page`; scope admin with `body.admin-dashboard`. Use consistent geometry: 18–28px for workspace shells/cards, 10–16px for controls, and pills only for statuses or compact navigation.

Override explicit light surfaces: sticky headers, auth cards and fields, active tabs, popular pricing cards, drop zones, status chips, feature sections, and modal shells. Keep public editorial hard edges distinct from authenticated workspace geometry while sharing color and typography.

### 3. Preserve data and DOM targets

Prefer CSS and body scopes before markup changes. Preserve form IDs, event handlers, endpoint strings, payload keys, session storage, route aliases, and billing controls.

When the same dataset appears in a hidden overview and a visible tab, never duplicate an ID. Give each target a unique ID and render intentionally into both; `getElementById` otherwise fills the first target, which may be invisible.

For Telegram status, expose only a boolean/configuration state and display metadata. Never expose the raw bot token in a status response or fixture.

### 4. Test authenticated states with fixtures

Serve the relevant root with `terminal(background=True)`. Use Playwright with a safe synthetic session and minimal API fixtures:

- profile/me returns a synthetic user and client;
- jobs/sync returns deterministic arrays;
- bot status returns a synthetic connected username without a token;
- admin endpoints return small deterministic stats and cards;
- generation calls are intercepted and never reach paid providers.

After initialization, force reveal-gated elements visible before full-page capture. Assert this invariant at every viewport:

```js
document.documentElement.scrollWidth === document.documentElement.clientWidth
```

Collect console errors, page errors, failed critical assets, redirects, duplicate IDs, and zero-sized critical elements.

### 5. Measure contrast and inspect hierarchy

Use computed styles and numeric luminance. Check body text, muted text on panels, labels, inactive/active tabs, form placeholders, status chips, error states, and text on accent buttons. Target 4.5:1 for normal text and 3:1 for large text/UI where practical.

Inspect at minimum the landing hero/mobile stack, login card/image, dashboard stats and bot card, Studio composer/output panels, and admin sidebar/overview/modals. Vision is a second opinion; computed color and DOM rectangles are the source of truth.

### 6. Review before release

Capture desktop and mobile previews for every affected family of surfaces. Keep the production release behind an explicit visual review checkpoint. If a shared stylesheet changes, version its URL so the browser and edge can distinguish the new theme from stale CSS, then verify the served HTML/CSS bytes after release.

## Pitfalls

- **Only changing `:root`.** Higher-specificity page rules and hard-coded backgrounds leave light islands. Add scoped overrides and inspect computed styles.
- **Active-tab inversion.** `background: var(--ink)` becomes a light active pill after dark tokens change. Set both background and foreground.
- **Dark descendant on dark section.** Old `var(--white)` text can resolve to a dark panel. Override the descendant, not just its parent.
- **Unauthenticated false negative.** Dashboard and Studio screenshots may show a redirect or empty shell. Fixture session/data endpoints first.
- **Duplicate hidden/visible IDs.** Data populates an invisible overview instead of the visible tab. Make target IDs unique.
- **Real provider calls during QA.** Intercept generation and status routes; never spend credits to test CSS.
- **Stale shared CSS.** Version the stylesheet URL and compare served bytes before rewriting correct styles.
- **Square/rounded collision.** Define a geometry contract for shells, controls, and pills; do not leave legacy zero-radius rules active by accident.

## Verification

- [ ] All affected routes and CSS sources were mapped.
- [ ] Shared and page-local cascade conflicts were handled.
- [ ] Dark tokens and explicit light declarations were overridden.
- [ ] DOM, auth, API, and payload contracts were preserved.
- [ ] Duplicate IDs and hidden/visible targets were checked.
- [ ] Fixture-backed desktop/mobile browser QA passed.
- [ ] No console/page errors or critical asset failures remain.
- [ ] No horizontal overflow exists at tested widths.
- [ ] Contrast ratios were measured numerically.
- [ ] Desktop and mobile previews were reviewed before release.

## References

- `references/scena-dark-portal-release.md` — Scena route matrix, dark tokens, fixture shapes, and review checks from the multi-surface rollout.
