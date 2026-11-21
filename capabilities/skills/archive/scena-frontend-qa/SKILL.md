---
name: scena-frontend-qa
description: Test Scena’s tenant dashboard and admin frontend surfaces.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    category: devops
    tags: [scena, frontend, telegram, admin, qa, browser]
    related_skills: [scena-full-checkup, scena-auth-client-sync-debug, authenticated-frontend-surfaces, headless-screenshot-qa]
---

# Scena Frontend QA Skill

Test Scena’s split client portal and admin frontend while preserving tenant isolation and existing API contracts. This skill focuses on reproducible UI/API verification; it does not handle credentials or production database writes.

## When to Use

- The portal shows stale credits, missing client data, or a false Telegram status.
- The admin control plane is being redesigned or gains a new operator panel.
- A responsive/authenticated surface needs browser QA rather than static inspection.
- A frontend change touches client lookup, bot state, tab navigation, modals, or workflow cards.

## Prerequisites

- The Scena repository and project guidance are available.
- Use `search_files` and `read_file` to trace the relevant HTML, Worker route, and tests before editing.
- Use `patch` for edits to existing files.
- Use `terminal` for the repository test runner and a local static server.
- Use `headless-screenshot-qa` or the browser tools for visual checks.
- Keep API tokens, Telegram tokens, admin passwords, and client secrets out of fixtures and output.

## How to Run

1. Classify the surface: client portal, admin control plane, or Operator Studio.
2. Trace the request from the DOM handler to the API route and tenant lookup.
3. Fix the contract at both ends, then add a real API regression test.
4. Run authenticated browser checks with context-level API fixtures.
5. Inspect desktop, mobile, and modal screenshots before reporting success.

## Quick Reference

| Surface | File | Live path | Core concern |
|---|---|---|---|
| Client portal | `pages/portal/dashboard.html` | `/dashboard` | tenant bot status and client state |
| Admin control plane | `pages/admin/index.html` | `/` | clients, brain, knowledge, settings |
| Operator Studio | `pages/admin/operator.html` | `/operator` | workflow construction and runs |

## Procedure

### 1. Trace tenant bot status correctly

The portal must not infer a tenant’s state from a global bot environment variable. Resolve the authenticated client first and read the client row’s bot fields. Keep configuration and liveness distinct: a stored token means configured unless the API explicitly performs a provider probe.

The tenant bot contract should be symmetric:

- `GET /api/client/bot` returns safe metadata such as `connected`, `telegram_bot_configured`, `bot_username`, `bot_name`, and chat ID. Never return the token.
- `POST /api/client/bot` accepts canonical `{ "bot_token": "…" }`; accept a legacy field only as a temporary compatibility bridge.
- `DELETE /api/client/bot` clears token, username, and chat ID on the current client row only.

The frontend must read `data.connected` or `data.telegram_bot_configured` and send `bot_token`. A secret-shaped response field is not a UI status contract.

### 2. Check the admin DOM as behavior, not text

Preserve live IDs and handlers unless the replacement updates all consumers. Eliminate duplicate IDs: an overview summary and a dedicated client tab need different targets, for example `overview-clients-grid` and `clients-grid`. If one data load feeds both, render into both explicit elements.

If tab code queries `.nav-tab[data-tab="..."]`, every tab button needs its matching `data-tab`. A page can look correct while clicks silently fail if the DOM contract is incomplete.

When a redesign removes a panel, remove its startup loader or guard its DOM write. Do not leave `getElementById(...).innerHTML` calls aimed at retired panels; browser console errors are regressions.

Expose actual existing capabilities in the admin surface. A Client Brain panel should call the existing brain API and show `Agent.md`, `Basic User.md`, overrides, and generated memory. A Knowledge Hub template action should call the workflow API instead of being a decorative button.

### 3. Build focused regression coverage

Run the Worker harness for the bot route with a name filter or the smallest relevant test selection. Assert the status response, absence of the raw token, tenant-row update, and absence of unintended writes to shared bot state. Run the existing admin and operator UI tests after DOM changes.

Do not use source-regex tests for new runtime behavior when an executable route or browser check is available. If the repository already has static contract tests, keep them aligned with actual behavior and add runtime coverage for the failure mode.

### 4. Run browser QA with stable fixtures

Serve the relevant static directory locally and route API calls at the browser **context** level, not just one page. This matters when the same QA run opens both desktop and 390px mobile pages.

Fixture checks should cover:

- authenticated startup hides the login overlay;
- `/api/client/bot` status renders the returned bot name;
- save captures `{ bot_token: value }`;
- admin tab navigation activates the requested pane;
- Client Brain opens and closes without an overlay deadlock;
- no `pageerror`, failed API requests, or horizontal overflow;
- mobile stats and cards remain visible after the same async loads as desktop.

### 5. Inspect screenshots deliberately

Review overview, client list, Client Brain modal, and Knowledge Hub at desktop width and 390px. Check clipping, contrast, card height, empty-state labeling, modal boundaries, and whether the visual hierarchy matches the requested admin role. An empty Workflow Runs card is acceptable only when it has a clear empty state, not when its loader failed.

## Pitfalls

- No `GET /api/client/bot` route means the portal’s default “Non connecté” can lie while Telegram still works.
- Sending `telegram_bot_token` to an API expecting `bot_token` makes the UI reconnect path fail.
- Global bot configuration is not proof that the tenant row is configured.
- Duplicate IDs make `getElementById` populate the first, potentially hidden, surface.
- A missing `data-tab` attribute breaks navigation without a visible rendering error.
- `page.route()` on one page does not mock a second page; route the browser context.
- A browser QA script can create false mobile failures if its second page does not receive the same fixtures.
- “No console error” is not enough: inspect screenshots, because zero-height or hidden content can still be technically valid DOM.

## Verification

The task is complete when:

- focused API and UI tests pass, with unrelated baseline failures separated;
- the browser reports no page errors or failed requests on tested paths;
- desktop, mobile, and modal screenshots have been reviewed;
- the raw Telegram token is absent from API response bodies and UI state;
- the tenant bot route, admin navigation, Client Brain, and Knowledge Hub actions are exercised rather than merely present in markup.

## References

- `references/scena-frontend-qa-contract.md` — durable route map, fixture shapes, regression assertions, and screenshot checklist.
