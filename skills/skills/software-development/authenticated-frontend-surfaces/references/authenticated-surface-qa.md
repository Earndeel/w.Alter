# Authenticated Surface QA Reference

This reference records a reusable reproduction pattern from a Scena login/dashboard/Studio review. It contains no credentials or user data.

## Cascade failure pattern

The affected pages had page-local dark tokens such as `--text: #f5f5f0`, followed by a shared light stylesheet. The shared stylesheet changed the page background and some component backgrounds but did not redeclare every inherited foreground. The Google OAuth anchor therefore retained a near-white foreground on a white panel. The Studio also had a later page-local block that explicitly forced `border-radius: 0` and hard black offset shadows, while other controls retained rounded values from the old theme.

The durable fix was:

1. Add an explicit body scope for the Studio and use the existing auth/dashboard body scopes.
2. Define complete scoped light-workspace tokens instead of relying on `:root` inheritance.
3. Override the Google OAuth foreground directly.
4. Use rounded workspace shells and controls consistently; reserve pills for statuses and compact navigation.
5. Replace hard rectangular offset shadows with soft elevation.

## Measured examples

For the cream workspace:

- Ink `#101010` on panel `#fffdf8`: approximately 18.72:1.
- Ink `#101010` on bright vermillon `#ff3b18`: approximately 5.34:1.
- White `#ffffff` on bright vermillon `#ff3b18`: approximately 3.56:1, which is insufficient for normal-sized button text.
- Muted text `#5d584f` on paper `#f4f0e8`: approximately 6.21:1.

Use the actual computed colors in the browser as the source of truth; these values are examples, not a license to skip measurement after a palette change.

## Fixture matrix

| Route state | Session fixture | Data fixture | Expected assertion |
|---|---|---|---|
| Login anonymous | session response has no `user` | none | auth tabs and form panels remain available |
| Dashboard authenticated | session response has a minimal user | profile, bot, sync return deterministic values | cards render and route does not redirect |
| Studio authenticated | session response has a minimal user | profile returns credits; pipeline POST is intercepted | preprompts build, payload preview opens, generation JSON is captured |
| Studio mobile | same authenticated fixture | same as desktop | two-column output grid stacks without horizontal overflow |

Do not return a user from the login fixture: the real page will correctly redirect to the dashboard, making a login interaction test fail for the right reason.

## Reusable Playwright checks

For each route and viewport, collect:

```js
({
  scrollWidth: document.documentElement.scrollWidth,
  clientWidth: document.documentElement.clientWidth,
  title: document.title,
})
```

Then inspect critical selectors with `getComputedStyle`: OAuth button, primary action, inputs, workspace shell, cards, tiles, workflow items, and muted descriptions. Assert no horizontal overflow, no console/page errors, and no failed critical asset requests.

For dynamic Studio content, wait for initialization and assert the preprompt item count before measuring radius or taking a screenshot. For generation, fill the brief, click the real button, intercept the pipeline POST, and compare the captured JSON to the pre-refactor contract.

## Review gate

Keep production unchanged until the user sees a local or preview screenshot of login and Studio at desktop and mobile widths. After approval, verify the deployment hash and fetch the served HTML/CSS bytes; a successful deployment command alone is not proof that the branded domain serves the new stylesheet.
