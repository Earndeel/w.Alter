---
name: authenticated-automation-operations
description: "Use for authenticated browser, vault, and remote ops."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [credentials, vault, browser, camoufox, remote, tunnels, authenticated]
---

# Authenticated Automation Operations

Use this class-level skill for secret-backed browser sessions, vault retrieval, Camoufox/Google Flow operations, remote hosts and tunnels, and authenticated product QA. Keep credentials, browser state, remote infrastructure, application state, and user-facing delivery as separate boundaries.

## Identity, authorization, and secrets

- Resolve the exact account, host, tenant, service, session, destination, and requested side effect before retrieving a secret or changing state.
- Keep master passwords, tokens, cookies, OTPs, API keys, signed URLs, and raw authenticated state in the approved vault or protected process memory; never print, log, screenshot, prompt, or persist them in reports.
- Unlock and synchronize the vault before searching; local cache state is not authoritative.
- Search by name, username, URI, and stable item ID, emit only non-secret metadata, and ask for a selection when multiple entries match. Retrieve only the explicitly requested field.
- Make encrypted backups before vault/server repair and keep them mode-restricted until every client or service has been re-verified.
- Treat authentication, credential issuance, account entitlement, browser session validity, application authorization, and recipient-visible success as independent gates.

## Browser and Camoufox lifecycle

- Check the active server health, flavor, port, endpoint contract, and live browser before using it; a listening process without a live browser is not healthy.
- Use one supervisor and one canonical persistent session. Do not clone a profile or start a second browser to solve a state problem; duplicate sessions create cookie, fingerprint, and intervention ambiguity.
- Prefer active `/session/*` and `/tab/*` contracts over guessed legacy routes, serialize restarts, close tabs in `finally`, and resume by durable task identity after a crash.
- For React/SPA controls, set route/init hooks before navigation, use the native value setter or real keyboard/input events, and re-snapshot after every navigation, portal, or rerender. Accessibility refs and coordinates are ephemeral.
- Check anti-bot signals independently: WebDriver, user agent, plugins/languages, WebGL/canvas, timezone, resolution, WebRTC, and exit IP. Report each signal; never claim perfect stealth from a passive check.
- Keep browser-control APIs and visual streams on authenticated private routes; never expose them publicly or place credentials in stream URLs.

## Human intervention and visual handoff

Keep the canonical browser session as the source of truth. For Monitor mode, disable pointer and keyboard input. For Intervene mode, pause or queue agent mutations, acquire a per-session manual lock, and only then grant input. On Resume, revoke input first, re-check health, URL, session/tab identity, and a fresh screenshot/snapshot, then release the lock. Never race human and agent actions.

If a visible handoff is required, bridge the headed canonical display through an authenticated private remote-desktop stream; do not attach Chromium CDP to a headless Firefox/Juggler process or clone its persistent profile.

## Google Flow and credit-consuming work

Separate read-only account/credit checks from generation. Refresh authenticated cookies immediately before checking, include the session-integrity cookies, inject into a unique temporary user, and prove the live account and exact balance from a refreshed profile snapshot. A tier badge, banner, prior balance, project card, queue message, or progress percentage is not a current balance or deliverable.

Before any paid action:

1. save and present the exact single-line prompt for explicit review;
2. confirm duration, aspect ratio, variants, model, reference order, output scope, and displayed cost;
3. take a fresh snapshot and verify direct Create mode, `Agent=false`, enabled submit, exact prompt, and actual attachment chips/media IDs;
4. click once and record the pre/post media IDs;
5. poll the current project route with bounded retries, treating explicit failure as failure until a new media ID appears;
6. download through the authenticated browser context, then run media metadata, full decode, audio/ASR, contact-sheet, continuity, typography, watermark, and forbidden-object QA;
7. assemble only validated source files and re-run final metadata and pixel checks.

Use real keyboard events for Slate/contenteditable prompts and one-line input to avoid accidental multiple submissions. Identify assets by media ID/current source, not title or card order. A successful UI toast, `READY` marker, play icon, or queued prose is not completion. Surface any additional credit cost before a retry.

## Remote hosts, tunnels, and services

- Resolve hostname, IP, cloud project/zone, tailnet identity, service version, and process owner before mutation; a reachable port is not proof of the intended administrative target.
- Use the least invasive authorized path, preserve application exports and infrastructure snapshots, and never overwrite the only backup or prune volumes without identity and rollback proof.
- Treat SSH shell/file access, VNC/Screen Sharing, application APIs, and infrastructure control as separate capabilities with separate verification.
- Bind local credential-bearing APIs through explicit loopback SSH tunnels or authenticated private routes. Never expose a secret-bearing proxy beyond loopback.
- For service repair, inspect mounts, images, compose layout, healthchecks, and redacted logs read-only; change only the named service, preserve data mounts, and verify real login/sync/decryption/display after the update.
- For cloud recovery, snapshot first, use a temporary least-privilege key/user, verify a real login rather than a metadata success line, and remove every temporary credential and override after acceptance.
- For VPN/exit routing, verify each hop's public IP and portal response, keep host routing unchanged unless explicitly approved, and treat anti-bot failure as distinct from geographic blocking.

## Tenant products and callbacks

For authenticated multi-tenant products, keep public, auth, client, studio, admin, and provider routes separate. Use synthetic tenant fixtures, never expose bot/API tokens in test data, and compare method/path/body/response end to end. A configured row is not proof of live provider connectivity.

Treat callback bodies as attacker-controlled. Resolve task IDs within tenant/provider scope, authenticate with a signature or authenticated provider status call, conditionally win exactly one terminal transition, inspect affected-row count, and perform refunds, delivery, workflow advancement, or customer callbacks only after the winning transition. Apply the same idempotence gate to pollers, retries, cron recovery, and cleanup.

For browser QA, wait for async initialization, record request/page errors, verify viewport/overflow/modal bounds/duplicate IDs and save payloads, then read back deployment bytes, authenticated rendering, and the exact target record. Preserve old provider fallbacks until the new route is proven with focused, migration, dry-run, and global tests.

## Completion contract

Report the exact account/session/host/tenant, evidence for every gate passed, protected or missing data, external writes and their read-back, artifact IDs and measured media facts, remaining uncertainty, and the cleanup state. Stop when target identity, approval, backup, session validity, or rollback cannot be proved; do not convert a process exit code, API acceptance, visible UI, or browser connection into success.
