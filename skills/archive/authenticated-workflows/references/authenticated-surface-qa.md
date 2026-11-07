# Authenticated surface QA reference

## Cascade and contract audit

Before styling a login, dashboard, Studio, or other authenticated page, identify body scopes, page-local styles, shared stylesheet order, CSS custom properties, critical IDs/classes, session redirects, fetch/EventSource endpoints, payload keys, route aliases, and neighboring tests. A later shared stylesheet does not override every inherited declaration from an earlier inline block; redeclare the complete scoped token set where needed.

Keep DOM and behavior contracts intact. Prefer scoped CSS and a body class before changing markup. Do not remove auth, billing, provider, route, or generation logic as part of a visual refactor.

## Fixture matrix

| State | Session/data fixture | Required evidence |
|---|---|---|
| Anonymous login | no user; no authenticated redirect | tabs, form controls, validation, and OAuth labels remain usable |
| Authenticated dashboard | minimal user/profile/bot/sync data | route stays loaded; cards and navigation render |
| Authenticated Studio | deterministic profile/credits; intercept generation POST | preprompts initialize; payload JSON remains unchanged |
| Mobile authenticated | same safe fixtures at narrow viewport | grid stacks; no horizontal overflow |

Wait for asynchronous initialization before measuring dynamic cards, preprompts, or output tiles. Do not return a user from the login fixture or the real app will redirect as designed.

## Visual and accessibility checks

Use computed browser colors, not vision alone. Resolve transparent backgrounds against the real nearest surface. Target 4.5:1 for normal text and 3:1 for large text; measure placeholders, muted text, inactive tabs, OAuth labels, status chips, and primary controls separately. Bright accents often need dark ink rather than white.

Use one geometry contract: rounded workspace shells, consistent control radii, and pills reserved for status/compact navigation. Remove accidental zero-radius rules, black offset blocks, and unexplained square/rounded collisions. Check `document.documentElement.scrollWidth === clientWidth`, critical element visibility, console/page errors, failed critical assets, and desktop/mobile screenshots after initialization.

## Deployment gate

Keep production unchanged until the authenticated local/preview state is visually reviewed. After approval, verify deployment project/target, deployment hash, served HTML/CSS bytes, custom-domain response, and cache behavior. A successful deploy command is not proof that the reviewed stylesheet is live.
