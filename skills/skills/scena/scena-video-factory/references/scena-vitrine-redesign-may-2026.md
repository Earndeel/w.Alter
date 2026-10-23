# Scena vitrine redesign pattern (May 2026)

Use this when Lucas asks to improve the public Scena website or turn the portal into a real multi-page marketing site.

## Context

Project: `/root/projects/scena-cloudflare/`
Public site / client portal: `pages/portal/`
Cloudflare Pages custom domain: `scena.walter-ai.cloud`

Lucas wants a visual review checkpoint before public site deployment. Backend/API hardening can be deployed after tests, but **do not deploy the redesigned vitrine to Pages production before showing screenshots/preview and getting feedback**.

## Proven structure

Keep the existing authenticated client dashboard and checkout contract inside `pages/portal/index.html`, but wrap it with a stronger marketing shell and add physical pages:

```txt
pages/portal/index.html       # homepage + preserved client dashboard/auth modal/scripts
pages/portal/studio.html      # Scena Studio / Telegram + dashboard
pages/portal/connect.html     # Scena Connect / SaaS API key pitch
pages/portal/pricing.html     # Studio credits + SaaS partner pricing
pages/portal/docs.html        # developer quickstart
pages/portal/contact.html     # integration request/contact
pages/portal/assets/scena-site.css
pages/portal/assets/scena-site.js
```

Design direction that fit the product: dark premium cinematic, between Runway / Linear / Stripe:
- near-black background, subtle grid/radial gradients
- Inter + JetBrains Mono
- tight large headlines, high contrast
- translucent cards with whisper borders
- API/code panels for Scena Connect
- accessible `prefers-reduced-motion`

## TDD guardrail

Add a dedicated vitrine regression test before redesigning:

```txt
tests/scena-vitrine.test.mjs
```

It should assert:
- shared nav links to `/studio.html`, `/connect.html`, `/pricing.html`, `/docs.html`, `/contact.html`
- every page has `data-page-shell`
- shared CSS exists and includes `cinema-grid` + `prefers-reduced-motion`
- Connect page shows `sk_scena_`, `Authorization: Bearer sk_scena_`, signed webhook copy, and Seedance 2.0
- homepage keeps checkout contract: custom plan, `custom_credits`, 100 credits / 19$, 250 credits / 49$, 50 credits = 9$, 1000 credits = 189$

Run:

```bash
node --experimental-strip-types --test tests/scena-vitrine.test.mjs tests/client-credit-checkout-ui.test.mjs
npm test
```

## Implementation pitfalls

- The existing `index.html` contains the auth modal and client dashboard scripts. If rebuilding the homepage, preserve:
  - `<!-- DASHBOARD --> ... <!-- SIGN IN MODAL -->`
  - auth modal + `<script>` section
  - checkout functions and custom pricing constants
- Avoid double `</body></html>` when splicing old modal/script into a generated homepage.
- Secondary pages do not define `showSignIn`; nav buttons must use `window.showSignIn ? window.showSignIn() : location.href='/'`, not `showSignIn ? ...`, or they can throw `ReferenceError`.
- Keep physical static pages simple. Cloudflare Pages can serve them directly without a build step.
- Local preview check:
  ```bash
  cd /root/projects/scena-cloudflare/pages/portal
  python3 -m http.server 4177 --bind 127.0.0.1
  ```
- HTTP smoke:
  ```bash
  python3 - <<'PY'
  import urllib.request
  base='http://127.0.0.1:4177'
  for p in ['/', '/studio.html', '/connect.html', '/pricing.html', '/docs.html', '/contact.html', '/assets/scena-site.css']:
      with urllib.request.urlopen(base+p, timeout=10) as r:
          print(p, r.status, len(r.read()))
  PY
  ```
- If the normal browser tool cannot launch because Chrome is missing, use Scrapling dynamic session screenshots or install agent-browser. Large screenshots may timeout in vision analysis; compress to JPEG previews with PIL if needed.

## Release pattern

After tests and preview:

```bash
git diff --check
npm test
git add -A
git commit -m "Harden Scena production and redesign marketing site"
git tag scena-p0-vitrine-preview-YYYY-MM-DD
```

Do **not** `wrangler pages deploy` / production deploy until Lucas approves the visual direction.