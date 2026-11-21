# Visual monitor and intervention handoff

Use this reference when Camoufox must become visible inside Hermes without losing the authenticated or anti-detection session.

## Architecture

```text
canonical Camoufox session
        │ headed browser display
        ▼
virtual display → x11vnc → websockify/noVNC → authenticated HTTPS
                                                │
                                                ▼
                                       Hermes preview rail
```

The Hermes preview remains a Chromium UI client; it is not the Camoufox engine. A Firefox/Camoufox process controlled through Playwright's Juggler protocol cannot be adopted by Chromium's CDP. Stream the headed display instead.

## Choose the mode

| Mode | Agent control | Human input | Use |
|---|---|---|---|
| Hidden | enabled | none | normal automation |
| Monitor | enabled | disabled | Monsieur watches the live session |
| Intervene | paused or queued | enabled | Monsieur completes a challenge or manual step |

A raw noVNC page is interactive by default. Add an input gate or a transparent input-blocking layer for Monitor; do not label an unrestricted VNC view read-only.

## Procedure

1. **Identify the source of truth.** Check the active Camoufox health/flavor and use the active `/tab/*` contract to resolve the exact session and tab. Record only non-sensitive identifiers needed by the relay.
2. **Choose the launch strategy.** Prefer starting the canonical browser in headed mode on its own virtual display and keeping automation attached to that same process/context. If the current worker is headless, perform an explicit, state-aware handoff; never launch a second process against the same persistent profile and assume cookies, storage, fingerprint state, or challenge state are identical.
3. **Expose the display.** Bridge the browser's virtual display with x11vnc and websockify/noVNC, then serve the viewer through an authenticated HTTPS/private route. Open that viewer URL in the Hermes preview rail, not the raw Camoufox API port. Keep Hermes' own dashboard/CUA display (commonly `:99`) untouched; use a dedicated display (for example `:100`) and bind the web gateway only to the current Tailscale address. A Tailscale-only HTTP viewer is private because the transport is encrypted by Tailscale, but do not broaden that bind without adding VNC/web authentication.
4. **Enter Monitor.** Keep pointer and keyboard events disabled. Continue normal agent work only if the user asked to watch rather than take control; serialize screenshot/viewer updates with browser actions.
5. **Enter Intervene.** Pause or queue agent mutations, acquire a per-session manual lock, then enable input. Show the user which tab/session is being shared and keep any sensitive challenge or credential entry inside the approved human-in-the-loop boundary.
6. **Resume safely.** Disable viewer input and release the manual lock before unpausing automation. Re-check browser health, current URL, active tab identity, and a fresh screenshot/snapshot; re-plan from that observed state rather than replaying stale clicks.
7. **Tear down.** Close the viewer and stop the per-session bridge when its reference count reaches zero. Close browser tabs only through the normal lifecycle and leave persistent session state under the supervisor's ownership.

## Session and security rules

- Keep the visual route private and short-lived; never put cookies, access tokens, passwords, or connection strings in query strings, screenshots, logs, or handoff metadata.
- Do not transfer `cf_clearance` between browsers. It is fingerprint-bound; let the canonical Camoufox session obtain its own challenge state.
- Treat a state export/import as a fallback handoff, not equivalent continuity: localStorage, sessionStorage, open-page state, WebAuthn, challenge cookies, and browser fingerprint state may not survive.
- Serialize human and agent input. Without a lock, a user click can race an automated click and corrupt the task state.

## Verification checklist

- [ ] Health, flavor, and active API contract were checked before the handoff.
- [ ] The viewer shows the exact target tab, not a newly created duplicate.
- [ ] Monitor mode rejects pointer/keyboard input.
- [ ] Intervention pauses or queues agent mutations before input is enabled.
- [ ] A manual URL or page change is visible through the same session/API tab.
- [ ] Resume revalidates URL, tab identity, health, and screenshot/snapshot before continuing.
- [ ] The bridge and viewer are closed when no viewer remains.