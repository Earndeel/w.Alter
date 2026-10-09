---
name: camoufox-operations
description: Use when Camoufox needs automation or live intervention. Keep the canonical session safe and observable.
tags: [camoufox, browser, automation, stealth, react, sessions]
metadata:
  hermes:
    tags: [camoufox, browser, automation, stealth, react, sessions]
---

# Camoufox Browser Operations

Use this umbrella for Camoufox Max lifecycle, authenticated and anti-bot browser automation, React SPA interaction, crash recovery, and stealth verification.

## Naming and layering

Treat **Camoufox** and **Camofox Browser** as distinct components. Camoufox (`camoufox` Python package, `camoufox-js`, or the Camoufox Max server) is the anti-detection Firefox browser/engine; Camofox Browser (`@askjo/camofox-browser`, `jo-inc/camofox-browser`) is a separate agent-facing API/MCP/orchestration layer that may package or use Camoufox. Finding Camoufox does not prove that Camofox Browser is installed, and installing Camofox Browser should be justified by a specific unique need such as direct MCP-client compatibility—not by stealth, persistence, humanization, monitoring, or manual intervention, which belong to the canonical Camoufox session and its visual bridge.

Verify the two layers separately before reporting installation status: identify the executable/package and the active service for Camoufox, then check the exact `@askjo/camofox-browser` package or Camofox entrypoint. Do not add a second browser process or clone the persistent profile merely to obtain an agent API; parallel sessions create state, cookie, and intervention-lock ambiguity.

## Lifecycle and isolation

Check `/health` and the active flavor/port before using the server; do not assume historical ports or endpoint families. Let one supervisor own the production service, isolate Node and Python caches, launch the browser eagerly, serialize restarts, and close tabs in `finally`. A listening process without a live browser is not healthy.

Use isolated sessions for navigation and keep cookies, tokens, request bodies, and credentials out of reports. Prefer the active `/tab/*` contract over guessed legacy routes, and retry the same operation only after a genuine transient server recovery rather than duplicating a mutation.

## SPA and React rules

Set route/init hooks before navigation. Prefer DOM evaluation or native input according to the active server's reliable boundary; React inputs require the native value setter or contenteditable event sequence. On crashes, restart once, re-check health and target state, then resume by durable task identity.

## Stealth verification

Check WebDriver, user-agent consistency, plugins/languages, WebGL/canvas, timezone, resolution, WebRTC, and IP independently. ARM servers may lack a real WebGL context even when spoofed parameters look plausible, so report each signal and never claim perfect anti-detect from a passive check.

## Visual monitoring and human intervention

When Monsieur asks to see, monitor, or intervene in a Camoufox session, preserve one canonical browser session as the source of truth. Do not try to attach Hermes's Chromium preview directly to a headless Firefox/Juggler process or clone its persistent profile; use a headed Camoufox display bridged through an authenticated remote-desktop stream (Webtop/Selkies with x11vnc/noVNC) and open that stream in the Hermes preview rail. The detailed handoff state machine and bridge recipe live in `references/visual-monitor-handoff.md`.

Before exposing a session, check the active Camoufox health/flavor/contract, resolve the exact session and tab, and verify that the visual bridge points at that same display. Keep **Monitor** input-disabled; when **Intervene** is requested, pause or queue all agent mutations before granting pointer/keyboard input and acquire a per-session manual lock. On **Resume**, revoke manual input first, re-check health, URL, and a fresh screenshot/snapshot, then release the lock and continue from the observed state. Close the stream and release the bridge when no viewer remains.

Bind the API and visual endpoint to an authenticated private route such as Tailscale or HTTPS with a short-lived session token; never expose the browser-control API publicly and never put cookies, tokens, or credentials in stream URLs or logs.

## Verification

Prove a real tab lifecycle, target navigation/content, requested DOM or screenshot evidence, and clean tab closure. Distinguish API transport, browser readiness, page compatibility, authentication, and stealth results. For a visual handoff, also prove that a manual navigation is visible through the same tab/session and that agent mutations are blocked during intervention. Respect site terms and use the approved human-in-the-loop boundary for sensitive interactions.

The curator-managed Max-server history is routed in `references/curator-camoufox-archive-routes.md`. The user-owned `camoufox-stealth-audit` source was not archived or modified; load it directly only when that user-owned procedure is explicitly needed.
