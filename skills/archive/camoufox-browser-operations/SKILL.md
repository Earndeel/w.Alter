---
name: camoufox-browser-operations
description: Use for Camoufox browser operations and stealth checks.
tags: [camoufox, browser, automation, stealth, react, sessions]
metadata:
  hermes:
    tags: [camoufox, browser, automation, stealth, react, sessions]
---

# Camoufox Browser Operations

Use this umbrella for Camoufox Max lifecycle, authenticated/anti-bot browser automation, React SPA interaction, crash recovery, and stealth verification.

## Lifecycle and isolation

Check `/health` and the active flavor/port before using the server; do not assume historical ports or endpoint families. Let one supervisor own the production service, isolate Node and Python Camoufox caches, launch the browser eagerly, serialize restarts, and close tabs in `finally`. A listening Node process without a live browser is not healthy.

Use isolated Camoufox sessions for navigation. Treat a passive Mac Brave profile as a source for permitted session data only; never attach automation to the user's live Brave CDP or copy its profile into a second browser.

## SPA and React rules

Use the active `/tab/*` contract and set route/init hooks before navigation. Prefer DOM evaluation or native browser input according to the active server's reliability; React inputs require the native value setter or contenteditable event sequence, and complex cross-origin frames may need browser-level mouse/keyboard endpoints. On crashes, restart once and retry the same operation; a 503/retry signal is not permission to duplicate a mutating action.

## Stealth verification

Test WebDriver, user-agent consistency, plugins/languages, WebGL/canvas, timezone, resolution, WebRTC, and IP separately. ARM servers may lack a real WebGL context even when spoofed parameters look plausible; do not claim perfect anti-detect from passive results. Respect site terms and route CAPTCHA or authenticated flows to the appropriate approved boundary.

## Verification

Prove server health with a real tab lifecycle, navigation, snapshot/evaluate/screenshot as applicable, target status/content, and clean tab closure. Keep cookies, tokens, request bodies, and credentials out of logs and reports. Distinguish API transport, browser readiness, page compatibility, and stealth score.

Exact Max-server and stealth-audit recipes are routed in `references/curator-camoufox-archive-routes.md`.
