---
name: hermes-desktop-remote-operations
description: Use when operating Hermes Desktop or remote client paths.
tags: [hermes, desktop, remote, gateway, voice, electron, ssh]
metadata:
  hermes:
    tags: [hermes, desktop, remote, gateway, voice, electron, ssh]
---

# Hermes Desktop and Remote Operations

Use this umbrella for Hermes Electron operations and the remote dashboard, TUI, and voice paths that feed it. Keep renderer, gateway, dashboard/API, relay, and local-permission layers distinct so transport success is not mistaken for application success.

## Desktop layer

Identify the installed compiled bundle, backend, relay, and supervised service before changing files. Diagnose blank windows, stale renderer state, host-header rejection, token failures, tunnel loss, plugin/theme problems, and remote setup one layer at a time. A source edit on the server does not change a compiled desktop binary without rebuild or runtime injection.

## Desktop navigation and embedded browser

When Monsieur asks how to open the browser or a side panel, classify the surface before answering: the embedded Hermes browser is not the native OS browser, and the visible Desktop preview is not the remote/headless browser backend. On macOS, use **⌘⇧L** to open the embedded browser tab, **⌘J** to toggle the right sidebar, **⌘B** to toggle the left sidebar, **⌘K** (or **⌘P**) for the command palette, and **⌘/** for the keybind panel; use the platform's Ctrl equivalent where Desktop maps `mod` to Ctrl. Do not transfer TUI bindings into Desktop: **Ctrl+J** is a multiline-input shortcut in the TUI, not the Desktop browser opener.

Verify shortcut claims against the current Desktop documentation and, when a checkout is available, `apps/desktop/src/lib/keybinds/actions.ts` plus `apps/desktop/src/app/hooks/use-keybinds.ts`; the source registry is authoritative for the action-to-key mapping. For an agent-requested visible page, use the Desktop preview operation and read the pane back to confirm it opened; do not describe a remote browser session as a visible app panel.

The reusable shortcut map and verification recipe live in `references/desktop-navigation-shortcuts.md`.

## Remote connectivity

The dashboard/API port is the client surface; the gateway messaging port's health endpoint is not a substitute. Prefer the current Desktop SSH connection mode or a loopback SSH tunnel, verify the actual dashboard port, and use `/api/status`, `/v1/models`, and authenticated `/api/ws`. Treat a direct non-loopback `Invalid Host header` as host middleware evidence when loopback is healthy; do not disable host validation or token checks globally.

## Voice diagnosis

Trace the actual path before changing providers: wake-word, batch STT→agent→TTS, desktop push-to-talk, and realtime speech-to-speech have different owners and failure modes. Identify which process owns the microphone, distinguish configured from registered providers, and prevent duplicate STT/TTS or wake events with correlation/state checks.

## Session-history display

When a user reports that old chats disappeared from Desktop, first distinguish the Home/project overview from the complete session data: a small number of rows can be a preview cap, not deletion. On builds that expose project grouping, open the sidebar display/filter menu, keep **Group by → Project**, and enable **Show all sessions**; verify the expanded rows before investigating profiles, backends, or storage.

If the control is absent or expansion remains incomplete, verify the Desktop build and active profile/backend, then inspect the renderer's session-preview and pagination logic rather than changing server source blindly. Treat frontend preview limits, backend page size, and search results as separate layers; enabling all sessions only expands sessions already loaded by that build.

The source-level clues and version caveats for this flow are kept in `references/session-history.md`.

## Verification

Verify each layer independently: process/config identity, dashboard/API health, authenticated HTTP, WebSocket, renderer state, audio-device ownership, provider registration, and final user-visible behavior. Preserve live processes when recovering and report the exact route used.

Exact remote-port, SSH/tunnel, token, and voice-debugging procedures are routed in `references/curator-desktop-remote-archive-routes.md`.
