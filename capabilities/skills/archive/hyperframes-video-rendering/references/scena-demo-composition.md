# Scena × HyperFrames Demo Composition (2026-05-11)

Live demo: https://eaa25e7f.hyperframes-demo.pages.dev
Repo: /root/projects/hf-demo/test-video/

## What it shows

The demo site has two panels:
- **Left**: Source code of the HyperFrames composition (HTML + data-attributes + GSAP timeline)
- **Right**: A player that executes the same timeline (like HyperFrames preview mode)
- **Pipeline steps**: Init → Compose → Preview → Lint → Render (visualized)
- **Controls**: Play/Pause/Reset with timecode display

## Key HyperFrames patterns demonstrated

1. `data-composition-id`, `data-start`, `data-duration`, `data-width`, `data-height` on root
2. `class="clip"` on every visible timed element
3. `data-track-index` for layering (0=background, 1=foreground)
4. GSAP timeline `paused: true` registered on `window.__timelines["main"]`
5. Deterministic rendering — no wall-clock, no Math.random(), no Date.now()

## Render failure on this machine

ARM64/aarch64 — chrome-headless-shell binary is x86_64. Render fails. Preview works.

## HyperFrames composition file

See `/root/projects/hf-demo/test-video/index.html` for the full composition (15s vertical video, 1080×1920, Scena-themed).
