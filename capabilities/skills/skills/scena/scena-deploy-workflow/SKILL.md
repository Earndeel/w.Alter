---
name: scena-deploy-workflow
description: "Scena deployment to Cloudflare Pages — the wrong-project trap, curl fallback, GSAP local serving, and common pitfalls."
version: 1.0.0
author: Lucas + W.Alter
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [scena, deploy, cloudflare, pages, gsap]
---

# Scena Deploy Workflow

Cloudflare Pages deployment patterns discovered during Scena development.

## The Wrong Project Trap

**CRITICAL: Always verify the Cloudflare Pages project name before deploying.**

During development, `wrangler pages publish` or API calls can target the wrong project if:
- Multiple projects exist in the same Cloudflare account
- The `project_name` in `wrangler.toml` doesn't match what you intended
- Environment variable `CLOUDFLARE_ACCOUNT_ID` points to the wrong account

**Before every deploy:**
```bash
# Verify which projects exist
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[].name'

# Verify the target project specifically
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/scena" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.name, .result.production_branch'
```

## curl Deploy (When wrangler Fails)

When wrangler's Node.js fetch fails (sandbox/ARM64 environments), deploy via REST API directly:

```bash
# 1. Create tarball of the build output
cd build_dir/ && tar -czf /tmp/scena-deploy.tar.gz .

# 2. Upload via API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/scena/deployments" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -F "file=@/tmp/scena-deploy.tar.gz"
```

## GSAP Static Serving

GSAP npm dist/ folder contains all plugins locally — do NOT use CDN. Copy to the static folder for Cloudflare Pages:
```bash
cp -r node_modules/gsap/dist/ public/vendor/gsap/
```

## Login Modal JS Crash

The `#nav-links` selector crash in the login modal happens when:
- The modal loads before the nav is rendered
- jQuery/CSS selector runs on a missing element

**Fix:** Wrap nav-dependent JS in `document.addEventListener('DOMContentLoaded')` or use optional chaining `document.querySelector('#nav-links')?.addEventListener(...)`.

## Pages `.html` Extension Stripping

Cloudflare Pages automatically redirects `.html` URLs to extensionless equivalents with a **308 redirect**:
- `/login.html` → `/login`
- `/operator.html` → `/operator`
- `/demo.html` → `/demo`

**Consequence:** All internal links and test assertions should use extensionless paths (`/login`, `/operator`, `/demo`). If tests match `href="login.html"`, they will break on Pages — match `href="/login"` instead.

## Scena Pages Projects

| Project | Domain | Purpose |
|---|---|---|
| `scena-portal` | `scena.walter-ai.cloud` | Client portal, login, interface, contact |
| `scena-admin` | `admin-scena.walter-ai.cloud` | Admin dashboard, Workflow Lab (operator) |
| `scena-connect` | — | SaaS Connect docs/partner pages |

**Always pass `--project-name`** to avoid the wrong-project trap.

## Client Video Interface Convention

For client-facing video workflow UI, use the product name **“Scena Interface”**, not “Demo Studio”. The visual target is a minimalist Higgsfield-like create-video shell: prompt/composer on the left, output board/canvas on the right, hidden/advanced provider/API details, and a visible primary `Generate` CTA above the fold. Keep `/demo` only as a legacy alias when useful, but canonical links should point to `/interface`.

See `references/scena-interface-preview.md` for the validated layout markers and preview/deploy sequence.

## Full Deploy Sequence (Portal + Admin + Worker)

A portal/auth fix often requires deploying **three** targets — Pages does NOT update the API worker:

```bash
# 1. Deploy portal pages
CLOUDFLARE_API_TOKEN=$(vault get cloudflare/api_token) \
  npx wrangler pages deploy pages/portal --project-name=scena-portal --commit-dirty=true

# 2. Deploy admin pages
CLOUDFLARE_API_TOKEN=$(vault get cloudflare/api_token) \
  npx wrangler pages deploy pages/admin --project-name=scena-admin --commit-dirty=true

# 3. Deploy API worker (SEPARATE — Pages deploy does NOT update this)
cd workers/api && CLOUDFLARE_API_TOKEN=$(vault get cloudflare/api_token) \
  npx wrangler deploy --name=scena-api
```

## Auth Endpoint Verification Pitfall

See `references/auth-flow-debugging.md` for full Google OAuth flow, session endpoints, and common failure patterns.

**`curl -sI` (HEAD) returns 404 on auth endpoints that only handle GET.** The `handleAuth` dispatcher checks `method === "GET"`, which does not match HEAD requests.

Always verify auth endpoints with a real GET:
```bash
# WRONG — sends HEAD, gets 404
curl -sI https://api.walter-ai.cloud/api/auth/google

# CORRECT — sends GET, shows 302 redirect to Google
curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}" https://api.walter-ai.cloud/api/auth/google
```

## Pre-Deploy: Visual Verification of the Artifact

Before running `wrangler pages deploy`, verify the local HTML renders correctly in headless Chromium. See `references/playwright-visual-verification.md` for the full recipe (Playwright setup, DOM measurement pass, screenshot pitfalls). Key lesson: trust DOM `getBoundingClientRect` heights over vision verdicts on full-page screenshots — vision models hallucinate empty sections on tall (>3000px) downscaled PNGs.

## Post-Deploy Verification (always do this)

After `wrangler pages deploy` returns a preview URL, **verify that the custom domain serves the same bytes as the preview** before claiming success. Cloudflare Pages can lag on the production alias if the deploy didn't promote correctly, or you can hit an edge cache.

```bash
# 1. Hit production custom domain
curl -s -o /tmp/prod.html -w 'HTTP %{http_code} · %{size_download}B\n' https://scena.walter-ai.cloud/

# 2. Hit the preview URL wrangler just gave you
curl -s -o /tmp/preview.html -w 'PREVIEW %{http_code} · %{size_download}B\n' https://<hash>.scena-portal.pages.dev/

# 3. Diff — must be identical
diff -q /tmp/prod.html /tmp/preview.html && echo 'PROD=PREVIEW OK'

# 4. Grep a marker only present in the new version (title, a new class, a unique string)
grep -c 'Instrument Serif\|new-marker-class' /tmp/prod.html
```

If prod ≠ preview, the deploy did not promote. Don't tell the user it's live until step 3 passes.

## GitHub Push Lockout — Don't Block on It

When `git push` to GitHub fails with `Permission denied (publickey)` and the actual goal is "ship to prod" (not "sync the repo"), **don't get stuck on GitHub auth**. Cloudflare Pages deploys from the local working tree via `wrangler pages deploy <dir>` — it doesn't need GitHub at all. Path:

1. Commit locally (`git commit`) so the work is recorded with a SHA.
2. Deploy directly to Pages with wrangler (uses `vault get cloudflare/api_token`).
3. Verify with the post-deploy block above.
4. Surface the GitHub auth issue to the user as a separate item — don't let it gate the deploy.

The Pages dashboard does NOT need the GitHub remote to be in sync. Direct upload is a first-class deploy mode.

## CF Worker Cron vs Hermes Cron

Scena has two types of scheduled triggers — don't confuse them:

| Trigger | Where | How to pause |
|---|---|---|
| **Hermes cron** | `hermes cron list` | `hermes cron pause <id>` |
| **CF Worker cron** | `wrangler.toml` → `[triggers]` → `crons` + source code handler | Edit source + redeploy worker |

The **Scena Sentinel** (daily checkup at 6h10 UTC) is a CF Worker cron, NOT a Hermes cron. To pause it:
1. Comment out the trigger call in `workers/api/src/index.ts` (e.g. `// await runScenaSentinelIfDue(...)`)
2. Redeploy: `cd workers/api && npx wrangler deploy`
3. The `*/1 * * * *` cron in `wrangler.toml` stays active — it also handles job recovery and webhook retries

## Pre-Deploy: Missing Export Check

**`provider_payloads.ts` is the shared utility file** — functions used by `agent.ts`, `saas_connect.ts`, and `workflow_admin.ts` must be exported from it. If a deploy fails with `No matching export`, the fix is adding the missing function to `provider_payloads.ts`, not importing from elsewhere.

Common missing exports pattern:
```
✘ [ERROR] No matching export in "src/provider_payloads.ts" for import "buildKieSeedanceVideoInput"
```

Fix: implement the function in `provider_payloads.ts` and export it. These are typically parameter-mapping helpers that transform workflow settings into provider-specific API payloads.

## Deploying the API Worker

The API worker (`workers/api/`) uses `wrangler deploy` (not Pages). It needs:
- `CLOUDFLARE_API_KEY` (Global API Key, not the scoped token) — `vault get cloudflare/global_api_key`
- `CLOUDFLARE_EMAIL` — `lucas.jouvencon@gmail.com`

**Shell vault pitfall:** When running in Hermes terminal, bare `vault get` may be intercepted by Hermes CLI. Use bash variable isolation:
```bash
CF_KEY=$(vault get cloudflare/global_api_key) && export CLOUDFLARE_API_KEY="$CF_KEY" && export CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" && npx wrangler deploy
```

## Environment Variables

- `CF_API_TOKEN` — Cloudflare API token (with Pages edit permission)
- `CF_ACCOUNT_ID` — Cloudflare account ID
- `CLOUDFLARE_API_KEY` — Global API Key (for Worker deploys)
- `CLOUDFLARE_EMAIL` — Account email (for Worker deploys)
- Available in vault: `vault get cloudflare/api_token`, `vault get cloudflare/account_id`, `vault get cloudflare/global_api_key`
