---
name: tailwind-v4-vite-react
description: Tailwind v4 + Vite + React project patterns — CSS-based config, @theme directive, @utility for animations, animated landing page techniques.
version: 1.0.0
author: walter
metadata:
  hermes:
    tags: [tailwind, vite, react, frontend, css, animations, landing-page]
    related_skills: [claude-design, popular-web-designs, gsap-frontend]
---

# Tailwind v4 + Vite + React Patterns

Use this skill when building a Vite + React + Tailwind v4 project (landing page, prototype, app). Covers the CSS-based configuration shift from Tailwind v3 and animated landing page techniques.

**Load alongside `claude-design`** for design process guidance, or `popular-web-designs` for brand reference.

**Reference files:** `references/deploy-and-write-patterns.md` — write_file corruption workaround, external model API calls for large components, Cloudflare deploy script pattern, video asset handling.

## Scaffolding

```bash
npm create vite@latest project-name -- --template react-ts
cd project-name
npm install -D tailwindcss @tailwindcss/vite
```

## Tailwind v4 Configuration

Tailwind v4 uses **CSS-based configuration** — no `tailwind.config.js` needed.

### vite.config.ts

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

### src/index.css — @theme directive

```css
@import "tailwindcss";

@theme {
  --font-podium: "Custom Font", serif;
  --font-inter: "Inter", sans-serif;
  --color-accent: #ff6b35;
}
```

This replaces `tailwind.config.js` theme.extend. All design tokens go here.

### Custom animation utilities — @utility directive

```css
@keyframes fade-up {
  from { opacity: 0; transform: translateY(30px); }
  to   { opacity: 1; transform: translateY(0); }
}

@utility animate-fade-up {
  animation: fade-up 0.8s ease-out forwards;
}

@utility animate-fade-up-delay-1 {
  animation: fade-up 0.8s ease-out 0.2s forwards;
  opacity: 0;
}
```

**v3 → v4 migration:** `@layer utilities` blocks become `@utility name { }` directives. Config file becomes `@theme { }` in CSS.

## Font Loading

Load fonts in `index.html` with `<link>` tags. Reference in CSS via `@theme` variables. Use in JSX with `font-custom` class (Tailwind auto-generates from `--font-custom`).

## Animated Landing Page Patterns

### 1. Film Grain Overlay
SVG noise as data URL, `steps(10)` keyframes for performance. `fixed inset-0 z-40 pointer-events-none opacity-[0.035]`.

### 2. Mouse-Following Spotlight
`useMousePosition` hook + `radial-gradient(600px circle at ${x}px ${y}px, rgba(255,255,255,0.04), transparent 60%)`.

### 3. Dot Grid Background
Array of 120 dots with randomized `animationDelay`. `dot-pulse` keyframes (opacity 0.2 → 0.8 → 0.2).

### 4. Scrolling Marquee
Repeated text in flex container with `translateX(0)` → `translateX(-50%)`. Parent `overflow-hidden`.

### 5. Animated Counters
`useCounter` hook with `requestAnimationFrame`. `IntersectionObserver` triggers counting when visible.

### 6. Corner Accent Lines
Gradient lines at viewport corners with staggered fade-up animations.

### 7. Live Status Badge
Pulsing ring: `scale(1)` → `scale(1.8)` with opacity fade on colored dot.

### 8. Vertical Side Text
`writing-mode: vertical-rl; text-orientation: mixed; transform: rotate(180deg);`

### 9. Scroll-Driven Video Playback

Map `video.currentTime` to scroll position for frame-by-frame scroll-linked animation.

```tsx
// In App.tsx
const videoRef = useRef<HTMLVideoElement>(null);
const scrollContainerRef = useRef<HTMLDivElement>(null);

useEffect(() => {
  const handleScroll = () => {
    if (!videoRef.current || !scrollContainerRef.current) return;
    const rect = scrollContainerRef.current.getBoundingClientRect();
    const scrollProgress = Math.max(0, Math.min(1, -rect.top / (rect.height - window.innerHeight)));
    videoRef.current.currentTime = scrollProgress * videoRef.current.duration;
  };
  window.addEventListener('scroll', handleScroll, { passive: true });
  return () => window.removeEventListener('scroll', handleScroll);
}, []);
```

Layout: outer `div` with `h-[300vh]` (scrollable area), inner `div` with `sticky top-0 h-screen` containing the `<video>` element.

```tsx
<div ref={scrollContainerRef} className="relative h-[300vh]">
  <div className="sticky top-0 h-screen w-full">
    <video ref={videoRef} src="/video.mp4" muted playsInline preload="auto" className="w-full h-full object-cover" />
  </div>
</div>
```

Video must use `preload="auto"` (not `preload="metadata"`) to ensure all frames are available for scrubbing. The video element needs `muted` and `playsInline` but NOT `autoPlay` or `loop` since playback is scroll-controlled.

## LLM-Assisted Code Generation

For large components (200+ lines), call an LLM API from `execute_code` instead of writing manually. See `references/deploy-and-write-patterns.md` for the external model API pattern.

**Model selection for code generation:**
- DeepSeek V4 Pro: excellent quality, but uses ~200 reasoning tokens per task (expensive for small tasks)
- DeepSeek V4 Flash: 1/16th cost of Pro, good quality, may need manual fixes (wrong URLs, inline components)
- Claude Sonnet 4: excellent, available via Kie.ai (free proxy)
- Gemini 3.5 Flash: free via Google direct API

**After generation, always verify:**
1. `export default` exists and component names match expectations
2. Asset URLs (images, videos, GIFs) are correct — LLMs invent placeholders
3. Code isn't truncated (`finish_reason: "length"` = increase `max_tokens`)
4. Markdown fences (```tsx) are stripped before writing to file

## Pitfalls

- **No tailwind.config.js in v4** — All theme customization is CSS-based via `@theme`. Don't create a config file.
- **@utility replaces @layer utilities** — Custom animation classes must use `@utility name { }` syntax.
- **Vite 8 + React 19 dev mode** — May show `$RefreshSig$ is not defined` error. Production build works fine. Build first to verify code, then serve production build.
- **Font class naming** — `--font-podium` in `@theme` generates `font-podium` class automatically. No manual registration needed.
- **write_file corruption with large TSX** — The `write_file` tool may corrupt large multi-line files (injecting line-number prefixes like `3|` into content). For files >100 lines, use `execute_code` with Python's `open().write()` to write reliably. This is critical for React components with complex JSX.
- **Video assets must go in `/public/`** — For Vite to serve video files as static assets, place them in `/public/` (e.g., `public/art-video.mp4`). Reference with absolute path in code (`/art-video.mp4`). Vite does NOT process video files through its asset pipeline.
- **`npm install` skips devDependencies with existing lockfile** — When a `package-lock.json` exists (e.g. after scaffolding), plain `npm install` may skip devDependencies (Vite, Tailwind, TypeScript). Use `npm install --include=dev` or verify with `npm ls --depth=0` before building. Symptoms: `vite.js` missing from `node_modules/vite/bin/`, build fails with `MODULE_NOT_FOUND`. This is especially common after adding a new dependency with `npm install <pkg>` which regenerates the lockfile.
