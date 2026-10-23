---
name: hyperframes-video-rendering
category: mlops
description: HyperFrames (HeyGen) — open-source HTML-to-MP4 video rendering framework. Write videos as HTML + GSAP timelines, render deterministically with Puppeteer + FFmpeg. Apache 2.0. Perfect for Scena's post-generation assembly pipeline.
tags: [video, rendering, hyperframes, heygen, gsap, html, mp4, ffmpeg, puppeteer, composition]
---

# HyperFrames Video Rendering

## What It Is

**HyperFrames** by HeyGen — 16.9k★, Apache 2.0. Framework that renders HTML compositions into MP4 videos deterministically.

> *"Write HTML. Render video. Built for agents."*

**Core idea**: A video is just an HTML file with `data-*` attributes + a GSAP timeline registered as `paused: true`. Puppeteer captures every frame; FFmpeg encodes to MP4.

## Why It Matters for Scena/Walter

Scena currently generates raw video assets (Kie/Fal/PiAPI) and delivers them directly. HyperFrames adds a **composition layer**:

```
Brief → AI generates assets (Kie/Fal/PiAPI)
     → HyperFrames assembles composition (HTML + GSAP timelines)
     → Render → MP4 with transitions, overlays, text, audio sync
     → Deliver to client
```

This turns Scena into **After Effects as a Service** — programmable, deterministic, agent-driven.

## Quick Start

```bash
# Requirements: Node.js >= 22, FFmpeg
npx hyperframes init my-video
cd my-video

# Preview in browser (live-reload studio)
npm run dev

# Lint composition
npm run check

# Render to MP4
npm run render
```

## Composition Structure

Every timed element needs three data attributes:

```html
<div id="root" data-composition-id="main" data-start="0" data-duration="15"
     data-width="1080" data-height="1920">

  <!-- Visible element: class="clip" is mandatory for visibility control -->
  <div id="title" class="clip" data-start="0.5" data-duration="5"
       data-track-index="1" style="font-size:72px;color:#fff">
    Hello World
  </div>

  <!-- Background video -->
  <video data-start="0" data-duration="15" data-track-index="0"
         src="bg.mp4" muted playsinline></video>

  <!-- Audio (separate from video) -->
  <audio data-start="0" data-duration="15" data-track-index="2"
         data-volume="0.5" src="music.wav"></audio>
</div>

<script>
  // GSAP timeline MUST be paused and registered
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from("#title", { opacity: 0, y: 60, duration: 0.9 }, 0.5);
  window.__timelines["main"] = tl;
</script>
```

## Key Rules

1. Every timed element needs `data-start`, `data-duration`, `data-track-index`
2. Visible elements MUST have `class="clip"` — framework uses this for visibility
3. GSAP timeline MUST be `paused: true` and registered on `window.__timelines`
4. Videos use `muted` with separate `<audio>` element
5. Only deterministic logic — no `Date.now()`, no `Math.random()`, no network fetches
6. Sub-compositions via `data-composition-src="compositions/file.html"`
7. **Run `npm run check` after every change** before considering the task complete

## Pipeline Steps

```
npx hyperframes init    → Create project (index.html + meta.json + package.json)
Edit index.html         → Add clips, GSAP timeline, styling
npm run dev             → Preview in browser studio (live reload)
npm run check           → Lint + validate + inspect
npm run render          → Puppeteer frame capture → FFmpeg encode → MP4
```

## 50+ Catalog Blocks

```bash
npx hyperframes add flash-through-white   # shader transition
npx hyperframes add instagram-follow      # social overlay
npx hyperframes add data-chart            # animated bar chart
```

Browse: https://hyperframes.heygen.com/catalog

## Agent Skills

HyperFrames ships Vercel Agent Skills to teach AI coding agents:

```bash
npx skills add heygen-com/hyperframes
```

Skills included: `hyperframes`, `hyperframes-cli`, `hyperframes-media`, `hyperframes-registry`, `gsap`, `animejs`, `css-animations`, `lottie`, `three`, `waapi`, `website-to-hyperframes`, `remotion-to-hyperframes`

## GSAP in HyperFrames

- Timeline MUST be `paused: true` (deterministic frame-seeking)
- Registered on `window.__timelines["composition-id"]`
- Library-clock animations (GSAP, Anime.js, Motion One) are **seekable and frame-accurate** — not wall-clock
- This is what makes deterministic rendering possible

## Post-Processing Filter Cookbook

See `references/ffmpeg-filters.md` for verified FFmpeg filter chains tested on ARM64:
- **Iphone lowlight look**: curves, rgbashift, vignette, noise — 0.35x realtime on ARM64
- **Auto-exposure pulse**: animated brightness/contrast via sin() expressions — 1.2x realtime

## Remotion Comparison

Remotion (React-based) was evaluated as an alternative. Same ARM64 Chrome limitation applies (both Puppeteer-based). Advantage: `--browser-executable` flag for custom Chromium, `remotion lambda` for cloud rendering. Conclusion: HyperFrames remains the primary assembly tool; FFmpeg filters handle post-processing that doesn't need frame composition. Both are complementary — HyperFrames for structural composition (HTML+GSAP), FFmpeg for pixel-level filters.

## Pitfalls

### ARM64 rendering failure (critical)
On ARM64/aarch64 servers, the Chrome headless-shell binary is x86_64 only. Tested workarounds (May 2026):
- `PUPPETEER_EXECUTABLE_PATH` — ignored by HyperFrames; it uses its own cache at `~/.cache/hyperframes/chrome/`
- Puppeteer `chromium@latest --platform linux_arm` — downloads x86_64 binary despite the platform flag (confirmed: ELF but links `/lib64/ld-linux-x86-64.so.2`)
- Replacing the binary with Puppeteer-installed ARM64 Chromium — binary is valid ELF but format differs (full Chrome ≠ headless-shell); render fails with "Syntax error" at launch
- Docker `--platform linux/amd64` — crashes on ARM host during Dockerfile build (`exec format error`)

**Only reliable solutions:** render on an x86_64 machine, or use a cloud x86_64 worker (e.g., GitHub Actions runner, Lambda). Preview mode (`npm run dev`) works fine on ARM64. See `references/hyperframes-pitfalls.md` for full details.

### Premium GSAP plugins not on CDN
SplitText, ScrambleText, DrawSVG, MorphSVG, ScrollSmoother are NOT on jsdelivr/unpkg (they ARE in npm `gsap@^3.13`). For CDN-heavy HyperFrames compositions, either self-host or stick to CDN-available plugins.

### Deterministic constraint
No `Date.now()`, `Math.random()`, or network requests in composition code. Same input = same output. Pre-generate dynamic data as JSON files.

### Large compositions
1080p × 15s at 30fps = 450 frames. Budget render time accordingly (seconds to minutes depending on complexity).

### `npm run check` mandatory
Run after every change. Fix all errors before render. Use `--strict` to block render on lint issues.

## Integration with Scena

Top-level architecture:

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
│ API Request  │ → │ Asset Gen    │ → │ HyperFrames  │ → │ MP4      │
│ (brief/photo)│    │ (Kie/Fal/    │    │ Composition  │    │ Delivery │
│              │    │  PiAPI/GPT)  │    │ + Render     │    │          │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────┘
```

Scena API endpoint would:
1. Accept composition template + assets
2. Generate HTML composition with data attributes
3. Call `hyperframes render` in Docker or worker
4. Return MP4 URL

## Linked Files

- `references/hyperframes-composition-example.html` — Complete demo composition (Scena-themed, GSAP animations, 15s vertical)
- `references/hyperframes-pitfalls.md` — Detailed render failure logs and fixes
