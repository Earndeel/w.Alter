---
name: hermes-tui-operations
description: Use when operating or debugging the Hermes TUI.
tags: [hermes, tui, ink, react, sessions, display, recovery]
metadata:
  hermes:
    tags: [hermes, tui, ink, react, sessions, display, recovery]
---

# Hermes TUI Operations

Use this class-level skill for TUI display customization, session overlays, input/focus failures, React rendering loops, and safe recovery.

## Display contract

Treat role glyphs/colors, reasoning rendering, tool/brand icons, status indicators, and live streaming as separate Ink/React surfaces. Inspect the current source map and build output before editing; a theme/display change should not be used to alter gateway or session semantics.

## Troubleshooting contract

Diagnose direct TUI, server tmux, and cmux attachment separately. Inspect process/session/database state before killing anything, because a blank pane or visible overlay does not prove a dead service. If the user-facing client is stuck, start a disposable recovery TUI in a new tmux session and preserve the old process; clean only the disposable repro session.

For `/sessions`, distinguish slow `state.db` queries from Ink focus/overlay event problems. For React update-depth failures, cap feedback state updates and reset the guard only when the effective range changes; run focused virtual-history tests.

## Verification

Build/run the affected TUI path, verify role/reasoning/tool rendering, exercise the relevant overlay or input path in a disposable session, and report whether old processes were preserved. Use session database evidence only for the layer it actually tests.

Exact display maps, recovery commands, and React overlay recipes are routed in `references/curator-tui-archive-routes.md`.
