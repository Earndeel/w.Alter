---
name: cloudflare
description: "Use first for any Cloudflare work (Pages, Workers, DNS, custom domains, tunnels, R2, D1, Workers AI): the credential rule and which procedure to open."
---

# Cloudflare — entry

## Credentials (the rule that cost the most debugging rounds)

- Never type, guess or paste a Cloudflare key. Run every Cloudflare command through
  `/root/.hermes/scripts/walter-cloudflare -- <command>`: it injects `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_EMAIL`,
  `CLOUDFLARE_API_KEY` (global key), `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_AI_TOKEN` without printing them.
- `walter-cloudflare check` verifies all of them (2026-11-01: global key + e-mail ok, API token ok, Workers AI token ok).
- The account e-mail is `CLOUDFLARE_EMAIL` in `~/.hermes/.env` (the vault item « W.Alter · cloudflare » has no e-mail
  field); a global key used with another e-mail answers « Unknown X-Auth-Key or X-Auth-Email ».
- The API token has no Workers AI permission: Workers AI uses `CLOUDFLARE_AI_TOKEN`.
- Older procedures still mention tokens read from `/root/.mcporter/mcporter.json` or a "read-only token": the helper
  above replaces all of that.

## Which procedure

| Need | Skill |
|---|---|
| Deploy a static site to Pages (wrangler, custom domain, production checks); REST-API fallback, D1 by API | `cloudflare-pages-deploy` |
| Deploy a Worker when wrangler's fetch fails | `cloudflare-worker-deploy-curl` |
| Point a custom domain at a Worker | `cloudflare-worker-custom-domain` |
| Anything through the Cloudflare MCP / mcporter (KV, R2, D1, Queues, Cron, Secrets, Analytics…) | `cloudflare-mcp-workers` |
| Expose a VM service with a named tunnel | `cloudflare-named-tunnel-setup` (the live tunnel config is `/root/.cloudflared/config.yml`) |
| R2 bucket for video files | `r2-setup-and-video-pipeline` (domain video) |
| Scena's Pages / Workers projects | `scena-deploy-workflow` (domain scena) |

In reserve (open with `skill_read`, it comes back automatically): `cloudflare-workers-custom-auth` (self-hosted auth
on Workers + D1 + Resend, Google OAuth, Stripe).

## Always

- Verify the target project/zone before deploying (multiple Pages projects exist; deploying to the wrong one is the
  classic trap), then check the production URL serves the new version.
- Public ingress for VM services goes only through the Cloudflare tunnel or Tailscale.
