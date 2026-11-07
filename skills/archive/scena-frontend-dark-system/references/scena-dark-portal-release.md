# Scena Dark Portal Release Reference

## Scope

This reference records the reusable details from the Scena multi-surface dark-theme rollout. It belongs under `scena-frontend-dark-system`; it is not a production deployment log.

## Route matrix

| Family | Local route | Body scope | Fixture needed |
|---|---|---|---|
| Public | `/index.html` | `data-page-shell` | no |
| Public | `/connect.html`, `/contact.html`, `/docs.html`, `/pricing.html`, `/studio.html` | `data-page-shell` | no |
| Auth | `/login.html` | `auth-page` | anonymous session |
| Client | `/dashboard.html` | `dashboard-page` | session, me, jobs, bot |
| Studio | `/interface.html` | `studio-page` | session/me, generation interception |
| Admin | `/index.html` under the admin root | `admin-dashboard` | admin token, stats, clients, integrations |

`demo.html`, `index-v2.html`, and `b.html` are separate self-contained dark artifacts; do not force the shared portal stylesheet into them unless they become the selected production route.

## Dark token baseline

```css
--paper: #07090d;
--paper-2: #0d1117;
--ink: #f4f2ea;
--muted: #969da6;
--line: rgba(255,255,255,.10);
--line-strong: rgba(255,255,255,.20);
--panel: #11151c;
--panel-2: #181e27;
--accent: #ff5a36;
--accent-soft: #ff9b82;
--success: #54d993;
--lime: #d7ff4a;
--blue: #8db5ff;
```

Observed contrast ratios for this baseline:

- body text on page background: `17.78:1`;
- muted text on panel: `6.68:1`;
- accent-soft on page background: `9.74:1`;
- dark CTA ink on coral: `6.39:1`;
- dark CTA ink on lime: `17.26:1`.

## Fixture shapes

Use synthetic data only. The client dashboard can render with:

```json
{
  "user": {"id": "qa-user", "name": "Lucas", "email": "qa@example.com"},
  "client": {"id": "qa-client", "credits": 120, "telegram_bot_username": "scena_qa_bot"}
}
```

Bot status should be secret-safe:

```json
{
  "connected": true,
  "telegram_bot_configured": true,
  "bot_name": "@scena_qa_bot",
  "bot_username": "scena_qa_bot"
}
```

Never put a Telegram token in a fixture, screenshot, response assertion, or reference file.

## Browser checks

For each route and at `1440x900` plus `390x844`:

1. wait for initialization/network idle;
2. force `[data-reveal]`, `.reveal`, and equivalent visibility gates on for capture;
3. assert `document.documentElement.scrollWidth === document.documentElement.clientWidth`;
4. collect console errors, page errors, failed requests, unexpected redirects, duplicate IDs, and zero-sized critical controls;
5. capture landing, login, dashboard, Studio, and admin evidence.

A successful Scena dark rollout produced zero page errors, zero failed critical requests, and no horizontal overflow across ten routes plus the mobile landing capture.

## CSS cache handling

All pages importing the shared portal stylesheet should use a dated query string when the shared design changes:

```html
<link rel="stylesheet" href="/assets/scena-site.css?v=dark-system-YYYYMMDD">
```

Verify both the source and served bytes before attributing a stale result to CSS. For Pages releases, keep an immutable deployment hash URL as the immediate verification target; also check the custom domain and both extensionless/extensionful routes.

## Staging hygiene

Stage files outside the deployed source directory. Include only the intended HTML routes, shared assets, and admin vendor assets. Exclude `.wrangler`, `.bak`, caches, generated screenshots, and experimental prototypes. Verify the staged HTML begins with `<!doctype html>` and contains no credentials before upload.
