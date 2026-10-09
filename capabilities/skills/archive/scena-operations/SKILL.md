---
name: scena-operations
description: Use when auditing or changing Scena product surfaces.
tags: [scena, cloudflare, d1, frontend, telegram, providers, security]
metadata:
  hermes:
    tags: [scena, cloudflare, d1, frontend, telegram, providers, security]
---

# Scena Operations

Use this umbrella for Scena's Cloudflare Worker/D1 product surfaces: frontend QA, authenticated portal state, dark visual consistency, provider migrations, and security-sensitive callback paths.

## Surface and tenant discipline

Keep public, auth, client, Studio, and admin routes distinct. Use synthetic fixtures and tenant-scoped data; never place Telegram tokens or other credentials in screenshots, responses, tests, or fixtures. Read the live contract before changing a route, and separate UI status from provider reachability.

For the portal bot contract, compare method/path/body/response end to end: GET returns safe configuration metadata, POST accepts the canonical `bot_token` shape, DELETE clears only the current client row, and no route returns the secret. A configured row is not proof of live Telegram connectivity.

## Frontend and visual QA

Run browser fixtures across desktop and mobile, wait for async initialization, record page/request errors, active tabs, dimensions, overflow, duplicate IDs, modal bounds, and save payloads. Inspect portal, Studio, admin, Client Brain, and Knowledge Hub separately. For dark changes, preserve shared tokens and cache-bust the served stylesheet; verify source bytes, deployment bytes, custom-domain routes, and authenticated rendering.

## Provider migration

Inventory every default, fallback, webhook, poller, cron recovery path, D1 seed, model catalog entry, and test before changing provider defaults. Preserve the old provider as fallback/legacy, align TypeScript and D1 seeds, keep legacy column names when compatibility requires them, and prove the new route's task correlation, status truth, idempotence, credits, and recovery. Run focused routing tests, migration-touched tests, Worker dry-run, then the global suite with unrelated failures separated.

## Callback and data security

Treat callback bodies as attacker-controlled. Resolve the exact provider task ID within tenant/provider scope, authenticate through signature or an authenticated provider status call, conditionally win one terminal transition, inspect affected-row count, and perform refunds, delivery, workflow advancement, or customer callbacks only after winning. Apply the same race/idempotence gate to pollers, cron recovery, retries, and cleanup.

Exact Scena frontend, portal, dark-system, provider-migration, and webhook recipes are routed in `references/curator-scena-archive-routes.md`.
