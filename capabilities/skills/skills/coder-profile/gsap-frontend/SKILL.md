---
name: gsap-frontend
category: coder-profile
description: GSAP animation skill for frontend coding — timelines, ScrollTrigger, Flip, plugins, React/Vanilla integration. Complements Motion (motion.dev) for complex sequencing, scroll-driven, and SVG animations.
tags: [gsap, animation, frontend, scrolltrigger, timeline, react, vanilla, svg]
---

# GSAP Frontend

## Purpose

Production-grade GSAP integration for the `coder` profile. Use when animations require:
- **Complex sequencing** (timelines with labels, nesting, precise timing)
- **Scroll-driven animation** (pinning, scrub, parallax — ScrollTrigger)
- **SVG morphing/drawing** (MorphSVG, DrawSVG, MotionPath)
- **Text effects** (SplitText, ScrambleText)
- **FLIP layout transitions** (Flip plugin)
- **Draggable/physics interactions**
- **Framework-agnostic control** (pause, reverse, seek, scrub to progress)

**When to use GSAP vs Motion:**
- **Motion** → React component animations, layout transitions, gestures, micro-interactions, AnimatePresence enter/exit
- **GSAP** → Complex timelines, scroll-driven, SVG, text effects, physics, when you need runtime control (play/pause/reverse/seek)

They can coexist: Motion for React component layer, GSAP for scroll/timeline/SVG layer.

**Stack default**: React 18+ / TypeScript / Tailwind CSS / GSAP 3.x / @gsap/react

---

## Installation

```bash
npm install gsap
# For React
npm install @gsap/react
```

GSAP is **100% free** since Webflow's acquisition — all plugins included in the public `gsap` npm package. No `.npmrc`, no auth token, no Club GSAP.

**Important: premium plugins are NOT on public CDNs.** `SplitText`, `ScrollSmoother`, `MorphSVGPlugin`, `DrawSVGPlugin`, `ScrambleTextPlugin`, `CustomEase`, and `ScrollToPlugin` do **not** exist on jsdelivr or unpkg. They only ship inside the `gsap` npm package under `node_modules/gsap/dist/`. For vanilla HTML deployments (Cloudflare Pages, etc.), copy them locally from the npm package.

### Vanilla HTML with all plugins (local files)

```bash
npm install gsap
mkdir -p js/
cp node_modules/gsap/dist/gsap.min.js \
   node_modules/gsap/dist/ScrollTrigger.min.js \
   node_modules/gsap/dist/ScrollSmoother.min.js \
   node_modules/gsap/dist/ScrollToPlugin.min.js \
   node_modules/gsap/dist/SplitText.min.js \
   node_modules/gsap/dist/ScrambleTextPlugin.min.js \
   node_modules/gsap/dist/DrawSVGPlugin.min.js \
   node_modules/gsap/dist/MorphSVGPlugin.min.js \
   node_modules/gsap/dist/MotionPathPlugin.min.js \
   node_modules/gsap/dist/Flip.min.js \
   node_modules/gsap/dist/Observer.min.js \
   node_modules/gsap/dist/CustomEase.min.js \
   node_modules/gsap/dist/EasePack.min.js \
   js/
```

```html
<script src="js/gsap.min.js"></script>
<script src="js/ScrollTrigger.min.js"></script>
<script src="js/ScrollSmoother.min.js"></script>
<script src="js/SplitText.min.js"></script>
<script src="js/ScrambleTextPlugin.min.js"></script>
<script src="js/DrawSVGPlugin.min.js"></script>
<script src="js/MorphSVGPlugin.min.js"></script>
<script src="js/MotionPathPlugin.min.js"></script>
<script src="js/Flip.min.js"></script>
<script>
  gsap.registerPlugin(ScrollTrigger, ScrollSmoother, SplitText,
    ScrambleTextPlugin, DrawSVGPlugin, MorphSVGPlugin,
    MotionPathPlugin, Flip);
  // Initialize smooth scroll
  const smoother = ScrollSmoother.create({
    wrapper: '#smooth-wrapper',
    content: '#smooth-content',
    smooth: 1.5,
    effects: true  // enables data-speed parallax
  });
</script>
```

### React / Vite

```bash
npm install gsap @gsap/react
```

```tsx
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { ScrollSmoother } from "gsap/ScrollSmoother";
import { SplitText } from "gsap/SplitText";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, ScrollSmoother, SplitText);
```

**Vite bundlers will tree-shake correctly.** All plugins import from the public `gsap` package — no special config needed.

---

## Core Patterns

### Pattern A: Single tween (vanilla)
```javascript
import { gsap } from "gsap";

gsap.to(".box", { x: 100, duration: 0.6, ease: "power2.inOut" });
gsap.from(".box", { opacity: 0, y: 30, duration: 0.5 }); // entrance
gsap.fromTo(".box", { x: 0 }, { x: 100, duration: 0.5 }); // explicit start/end
gsap.set(".box", { x: 100 }); // instant apply
```

### Pattern B: Timeline (sequencing)
```javascript
const tl = gsap.timeline({ defaults: { duration: 0.5, ease: "power2" } });

tl.to(".a", { x: 100 })
  .to(".b", { y: 50 }, "+=0.2")     // 0.2s after previous ends
  .to(".c", { opacity: 0 }, "-=0.1") // 0.1s before previous ends
  .to(".d", { scale: 1.2 }, "<");    // same start as previous

// Labels for readable sequencing
tl.addLabel("intro", 0);
tl.addLabel("outro", "+=0.5");
tl.play("outro"); // start from label
```

### Pattern C: ScrollTrigger (scroll-driven)
```javascript
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
gsap.registerPlugin(ScrollTrigger);

// Basic: trigger tween on scroll
gsap.to(".box", {
  x: 500,
  scrollTrigger: {
    trigger: ".box",
    start: "top center",
    end: "bottom center",
    scrub: true, // link progress to scroll
    toggleActions: "play reverse play reverse"
  }
});

// Pin a section while animating
gsap.to(".pinned-content", {
  y: -200,
  scrollTrigger: {
    trigger: ".section",
    start: "top top",
    end: "+=500",
    pin: true,
    scrub: 1
  }
});

// Batch: animate elements as they enter viewport
ScrollTrigger.batch(".card", {
  onEnter: (elements) => {
    gsap.to(elements, { opacity: 1, y: 0, stagger: 0.15 });
  }
});
```

### Pattern D: React integration (useGSAP)
```tsx
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useRef } from "react";

gsap.registerPlugin(ScrollTrigger);

function MyComponent() {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    gsap.to(".box", { x: 100 });
    
    gsap.timeline({
      scrollTrigger: {
        trigger: ".section",
        start: "top center",
        scrub: true
      }
    }).to(".panel", { x: 200 });
  }, { scope: containerRef });

  return <div ref={containerRef}>...</div>;
}
```

**Rules:**
- Always pass `scope` (ref) to contain selectors
- `useGSAP` handles cleanup automatically (reverts on unmount)
- Register plugins **once** at app top-level, not inside components

### Pattern E: React with gsap.context (fallback)
```tsx
import { useEffect, useRef } from "react";
import { gsap } from "gsap";

function MyComponent() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      gsap.to(".box", { x: 100 });
    }, containerRef);
    return () => ctx.revert(); // cleanup
  }, []);

  return <div ref={containerRef}>...</div>;
}
```

### Pattern F: Vanilla HTML (CDN)
```html
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrollTrigger.min.js"></script>
<script>
  gsap.registerPlugin(ScrollTrigger);
  gsap.to(".box", { x: 100, scrollTrigger: { trigger: ".box", start: "top center" } });
</script>
```

---

## Transform Best Practices

- **Prefer GSAP transform aliases** over raw `transform` string:
  - `x`, `y`, `z` → translate
  - `xPercent`, `yPercent` → percentage translate (works on SVG)
  - `scale`, `scaleX`, `scaleY`
  - `rotation` (deg), `rotationX`, `rotationY`
  - `skewX`, `skewY`
  - `transformOrigin`
- **Use `autoAlpha`** instead of `opacity` for fade — sets `visibility: hidden` at 0
- **Relative values**: `x: "+=20"`, `rotation: "-=30"`
- **Directional rotation**: `rotation: "-170_short"` (shortest path)

---

## Plugin Quick Reference

| Plugin | Use | Import |
|--------|-----|--------|
| ScrollTrigger | Scroll-driven animations | `gsap/ScrollTrigger` |
| ScrollToPlugin | Smooth scroll to element | `gsap/ScrollToPlugin` |
| ScrollSmoother | Momentum smooth scroll | `gsap/ScrollSmoother` |
| Flip | Layout transitions (FLIP) | `gsap/Flip` |
| Draggable | Drag interactions | `gsap/Draggable` |
| SplitText | Text splitting animations | `gsap/SplitText` |
| ScrambleText | Text scramble effect | `gsap/ScrambleText` |
| MorphSVG | SVG shape morphing | `gsap/MorphSVGPlugin` |
| DrawSVG | SVG stroke drawing | `gsap/DrawSVGPlugin` |
| MotionPath | Animate along SVG path | `gsap/MotionPathPlugin` |
| CustomEase | Custom easing curves | `gsap/CustomEase` |
| Observer | Unified pointer events | `gsap/Observer` |

**All free** — import from `gsap/PluginName` after `npm install gsap`.

---

## GSAP + Motion Coexistence

Use GSAP for scroll/timeline/SVG, Motion for React component animations:

```tsx
import { motion, AnimatePresence } from "motion/react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { useRef } from "react";

gsap.registerPlugin(ScrollTrigger);

function HybridComponent() {
  const sectionRef = useRef<HTMLElement>(null);

  // GSAP: scroll-driven timeline
  useGSAP(() => {
    gsap.timeline({
      scrollTrigger: {
        trigger: sectionRef.current,
        start: "top center",
        end: "bottom center",
        scrub: true
      }
    }).to(".gsap-element", { x: 200, rotation: 360 });
  }, { scope: sectionRef });

  // Motion: component hover + AnimatePresence
  return (
    <section ref={sectionRef}>
      <motion.div
        className="motion-element"
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        Hover me (Motion)
      </motion.div>
      <div className="gsap-element">
        Scroll drives me (GSAP)
      </div>
    </section>
  );
}
```

---

## Performance

- Animate **transform** and **opacity** primarily
- Use `will-change: transform` in CSS for animated elements
- Use `gsap.quickTo()` for frequently updated values (mouse followers)
- Call `ScrollTrigger.refresh()` only when layout actually changes
- Kill/revert animations on unmount (`ctx.revert()` or `useGSAP` auto-cleanup)

---

## Cloudflare Pages Deployment (Vanilla + GSAP)

For a static landing page using premium GSAP plugins on Cloudflare Pages:

```bash
# 1. Install GSAP locally
npm install gsap

# 2. Copy all plugin files into your project
mkdir -p dist/js
cp node_modules/gsap/dist/*.min.js dist/js/

# 3. Reference locally in HTML
# <script src="js/gsap.min.js"></script>
# <script src="js/ScrollTrigger.min.js"></script>
# ... etc

# 4. Deploy
cd dist && wrangler pages deploy . --project-name=my-site
```

**Do NOT** try to load premium plugins from jsdelivr or unpkg — they will 404. Only `gsap.min.js`, `ScrollTrigger.min.js`, `MotionPathPlugin.min.js`, `Flip.min.js`, `Observer.min.js`, and `EasePack.min.js` exist on public CDNs. Everything else must be copied from `node_modules/gsap/dist/`.

---

## FIRST LOADING RULE

**Load this skill BEFORE building ANY landing page, frontend, or animated UI.** The user has been caught waiting while the agent built 2-3 vanilla HTML iterations before loading this skill. The user expects GSAP premium plugins (SplitText, ScrollSmoother, DrawSVG) to be in play from the start.

**Vanilla HTML + GSAP pattern (no build step):**
1. `npm install gsap` in the project directory
2. `mkdir -p js/` and copy from `node_modules/gsap/dist/*.min.js`
3. Reference local `js/gsap.min.js` etc. in HTML `<script>` tags
4. Register plugins BEFORE any gsap.to() calls

**Do NOT** try to load premium plugins from jsdelivr/unpkg — they 404. Only basic plugins exist on public CDNs.

## Pitfalls

- **Premium plugins 404 on CDNs** — `SplitText`, `ScrollSmoother`, `MorphSVGPlugin`, `DrawSVGPlugin`, `ScrambleTextPlugin`, `CustomEase`, `ScrollToPlugin` are npm-only. Copy from `node_modules/gsap/dist/`.
- **ScrollSmoother requires specific DOM structure** — needs `#smooth-wrapper` and `#smooth-content` elements. See docs for exact setup.
- **GSAP without premium plugins looks basic** — if the user says animations are "décevantes" / disappointing, you are probably only using core tweens. Add SplitText (text reveals), ScrollSmoother (smooth scroll), MorphSVG (shape morphing), DrawSVG (stroke drawing), or ScrollTrigger pin/scrub for the wow factor.
- **ScrollTrigger batch() does NOT accept `animation`** — only `triggers`, standard config, and callbacks. Do not pass `animation` or `scrub` to `ScrollTrigger.batch()`.
- **SplitText chars/words need `overflow: hidden` wrappers** for clean clip/mask reveals — wrap each split element in a container with `overflow: hidden` before animating `y` or `rotateX`.
- **Flip requires elements to be in the same parent** for `absolute: false`. Use `absolute: true` when reparenting or reordering across containers.
- **MorphSVG needs `convertToPath()`** on non-path elements (circles, rects, polygons) before morphing.
- **Register plugins BEFORE any GSAP code runs** — do not call `gsap.to()` before `gsap.registerPlugin()`.
- **In React, register once at app level** — never inside a component that re-renders.
- **ScrambleTextPlugin destroys HTML markup inside elements** — `gsap.from(el, { scrambleText: { text: el.innerHTML } })` replaces the element's textContent with scrambled characters, stripping all `<br>`, `<span>`, `<em>`, and other inline tags. The rendered output becomes raw visible HTML source code (e.g. `Tes pubs vidéo, <br> <span class="...`). **Never use ScrambleTextPlugin on elements that contain HTML markup** — only use it on plain-text elements. For elements with inline tags (gradient spans, line breaks, italic accents), use `gsap.from(el, { opacity: 0, y: 30 })` or animate child elements individually with SplitText (which preserves markup structure). If a scramble effect is truly needed on a multi-tag headline, split the headline into separate plain-text wrapper elements and scramble each one independently.

---

## Trigger Terms

Load this skill when the user mentions:
- GSAP, GreenSock, ScrollTrigger, timeline
- scroll animation, pin section, scrub, parallax
- SVG animation, morphing, draw SVG
- text animation, split text, scramble text
- draggable, flip animation, layout transition
- complex sequencing, animation timeline
- smooth scroll, scroll smoothing
- disappointed animations, "décevant", basic animations

## Risk Level

**LOW** — GSAP is an animation library with minimal security surface.

## Linked Files

- `references/gsap-quick-reference.md` — Complete API quick reference and common patterns
- `references/scena-landing-patterns.md` — Production example: Scena landing page live patterns (ScrollSmoother, SplitText 3D, DrawSVG, pinned panels)
- `references/gsap-cdn-plugin-availability.md` — Which plugins exist on public CDNs vs npm-only
- `references/user-expectations.md` — When users find animations "basic" or "disappointing", what to add
- `templates/cinematic-landing.html` — Starter template with ScrollSmoother, SplitText, pinned panels, DrawSVG, custom cursor, grain/vignette, parallax orbs. Copy and customize.
