---
name: scroll-driven-video
category: creative
description: 'Scroll-driven video playback in React — video.currentTime synced to scroll via requestAnimationFrame, split layouts, sticky video panels, 9:16 portrait integration.'
tags: [video, scroll, react, landing-page, interactive, vite, tailwind]
---

# Scroll-Driven Video

Interactive web pages where a video's `currentTime` is directly mapped to the user's scroll position. The video acts as a scrubable timeline — scroll down to advance, scroll up to rewind. No autoplay, no loop.

## Use Cases
- Creative agency landing pages (Vanguard, portfolio sites)
- Product reveals / storytelling pages
- Artist / filmmaker showcase pages
- Any "cinematic scroll" experience

## Stack
- React + Vite + TypeScript
- Tailwind CSS
- Lucide-react (icons)
- Deployed to Cloudflare Pages

## Core Pattern: rAF-based Video Seeking

**CRITICAL**: NEVER use React `useState` + `useEffect` to drive video seeking. React batches state updates, causing stuttering and broken backward scrubbing.

### ❌ WRONG (stutters, doesn't rewind)
```tsx
const [progress, setProgress] = useState(0);

useEffect(() => {
  const handleScroll = () => {
    const scrolled = window.scrollY / (document.documentElement.scrollHeight - window.innerHeight);
    setProgress(Math.max(0, Math.min(1, scrolled)));
  };
  window.addEventListener('scroll', handleScroll, { passive: true });
  return () => window.removeEventListener('scroll', handleScroll);
}, []);

useEffect(() => {
  if (videoRef.current && ready) {
    videoRef.current.currentTime = progress * videoRef.current.duration;
  }
}, [progress, ready]);
```

### ✅ CORRECT — Basic (smooth, bidirectional, video element)

This works for simple cases. For production-quality scrubbing, use the Canvas-based pattern below.

```tsx
function VideoPanel({ scrollContainerRef }: { scrollContainerRef: React.RefObject<HTMLDivElement | null> }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const readyRef = useRef(false);
  const rafRef = useRef(0);

  useEffect(() => {
    const el = scrollContainerRef.current;
    const video = videoRef.current;
    if (!el || !video) return;

    const onLoaded = () => { readyRef.current = true; };
    video.addEventListener('loadedmetadata', onLoaded);

    const tick = () => {
      if (readyRef.current && video.duration) {
        const scrollable = el.scrollHeight - el.clientHeight;
        const raw = scrollable > 0 ? el.scrollTop / scrollable : 0;
        const progress = Math.max(0, Math.min(1, raw));
        video.currentTime = progress * video.duration;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      video.removeEventListener('loadedmetadata', onLoaded);
      cancelAnimationFrame(rafRef.current);
    };
  }, [scrollContainerRef]);

  return (
    <video
      ref={videoRef}
      src="/art-video.mp4"
      muted
      playsInline
      preload="auto"
      className="w-full h-full object-cover"
    />
  );
}
```

### ✅ BEST — Canvas + Lerp + Seek Gating (production quality)

Smoothest possible scrubbing: canvas rendering, lerp interpolation, seek gating. See [Canvas-Based Rendering](#canvas-based-rendering-smoother-than-video-element) below for full implementation.

**Why this works**:
- `requestAnimationFrame` runs at 60fps, bypassing React's render cycle entirely
- `video.currentTime` is set directly from scroll position — no state, no re-render
- Bidirectional: scrolling up decreases `scrollTop`, which decreases `currentTime`
- `readyRef` prevents seeking before metadata is loaded

## Video Element Requirements

```html
<video
  ref={videoRef}
  src="/video.mp4"
  muted           <!-- REQUIRED: allows programmatic seeking without user gesture -->
  playsInline     <!-- REQUIRED: prevents fullscreen on mobile -->
  preload="auto"  <!-- REQUIRED: loads full video for instant seeking -->
  <!-- NO autoplay, NO loop — scroll controls everything -->
/>
```

## Split Layout: Content Left, Video Right

The most common layout for scroll-driven video:

```
┌──────────────────────┬───────────────┐
│                      │               │
│   Scrollable Content │   Sticky      │
│   (60-65% width)     │   Video       │
│                      │   (35-40%)    │
│   Hero               │               │
│   Gallery            │   9:16 ratio  │
│   Process            │               │
│   Stats              │               │
│   Footer             │               │
│                      │               │
└──────────────────────┴───────────────┘
```

### Implementation

```tsx
<div className="flex min-h-screen">
  {/* Left: scrollable content */}
  <div ref={scrollContainerRef} className="w-[60%] overflow-y-auto h-screen">
    {/* Hero, gallery, process, stats, footer sections */}
  </div>

  {/* Right: sticky video */}
  <div className="w-[40%] h-screen sticky top-0">
    <div className="h-full flex items-center justify-center p-6">
      <div className="relative w-full max-w-[280px] rounded-2xl overflow-hidden border border-white/10">
        <div className="aspect-[9/16]">
          <VideoPanel scrollContainerRef={scrollContainerRef} />
        </div>
      </div>
    </div>
  </div>
</div>
```

### Key CSS
```css
/* Scrollbar hidden on content column */
.scrollbar-hide::-webkit-scrollbar { display: none; }
.scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }

/* Scanline overlay for video */
.scanlines::after {
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(0,0,0,0.05) 2px, rgba(0,0,0,0.05) 4px
  );
  pointer-events: none;
}
```

## Mobile Behavior

On mobile (< 768px), switch to stacked layout:
- Content on top (scrollable)
- Video below or as a fixed bottom panel
- Or: video becomes full-width at top of page, content scrolls beneath

```tsx
<div className="flex flex-col md:flex-row min-h-screen">
  <div className="w-full md:w-[60%] ...">
  <div className="w-full md:w-[40%] md:sticky md:top-0 ...">
</div>
```

## Visual Polish

- **Glow effect**: `box-shadow: 0 0 60px rgba(255,0,64,0.15)` around video frame
- **Scanlines**: Subtle repeating gradient overlay
- **Progress indicator**: A thin bar at bottom showing scroll progress
- **Label**: Artist name / video title below the video frame
- **Border**: `border border-white/10` with `rounded-2xl` for clean integration

## Deployment with Video

1. Place video in `public/` folder (Vite copies to `dist/` automatically)
2. Reference as `src="/video.mp4"` (absolute path from public root)
3. Build: `node node_modules/vite/bin/vite.js build`
4. Deploy: `wrangler pages deploy dist --project-name=<name>`
5. Video is served from Cloudflare CDN — fast globally

**PITFALL**: Large videos (>25MB) may slow deployment. Compress with FFmpeg if needed:
```bash
ffmpeg -i input.mp4 -vf scale=720:-2 -c:v libx264 -crf 23 -preset fast output.mp4
```

## Pitfalls

1. **React state seeking is ALWAYS wrong** — use rAF + direct `currentTime` assignment
2. **Video must be paused** — if video has `autoplay`, it fights the scroll seeking
3. **`preload="auto"` is mandatory** — without it, seeking fails because duration is unknown
4. **`muted` is mandatory** — browsers block programmatic seeking on unmuted video without user gesture
5. **Backward scrubbing**: Some MP4s have non-linear keyframe placement, causing choppy backward seeking. Re-encode with `-movflags +faststart` to fix:
   ```bash
   ffmpeg -i input.mp4 -c:v libx264 -crf 23 -movflags +faststart output.mp4
   ```
6. **Portrait video (9:16)**: Use `aspect-[9/16]` container, `object-cover` on video. Don't let the video stretch to fill — constrain with aspect ratio.
7. **Scroll container**: The `scrollContainerRef` must point to the element that actually scrolls (usually the left column with `overflow-y-auto`), NOT `window`.

## Critical Additions (from production debugging)

### Video Re-encoding with GOP=1

**THE #1 FACTOR for smooth seeking is keyframe interval.** Default H.264 encodes place a keyframe every 250 frames. Seeking to a non-keyframe frame forces the browser to decode from the last keyframe — this is slow, choppy, and breaks backward scrubbing.

**MANDATORY**: Re-encode with `-g 1` (keyframe every frame):
```bash
ffmpeg -i input.mp4 \
  -c:v libx264 -crf 23 -preset fast \
  -g 1 \
  -movflags +faststart \
  -vf "scale=720:-2" \
  output.mp4
```

- `-g 1` = GOP size 1 = every frame is a keyframe → instant seeking to any frame
- File size increases ~30-50% vs default GOP, but seeking is buttery smooth
- Without this, NO amount of JS optimization will make seeking smooth
- `-movflags +faststart` moves the moov atom to the beginning for progressive loading

### Canvas-Based Rendering (smoother than video element)

Displaying a `<video>` element directly causes visible flicker during seeking because the browser renders the nearest decodable frame, then updates when the seek completes. Drawing to a `<canvas>` eliminates this:

```tsx
function VideoPanel({ scrollContainerRef }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const readyRef = useRef(false);
  const rafRef = useRef(0);
  const currentRef = useRef(0);
  const seekingRef = useRef(false);

  useEffect(() => {
    const el = scrollContainerRef.current;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!el || !video || !canvas) return;
    const ctx = canvas.getContext('2d')!;

    video.addEventListener('loadedmetadata', () => {
      readyRef.current = true;
      video.currentTime = 0;
    });

    video.addEventListener('seeked', () => {
      // Draw frame to canvas after each seek completes
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0);
      seekingRef.current = false;
    });

    const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

    const tick = () => {
      if (readyRef.current && video.duration) {
        const scrollable = el.scrollHeight - el.clientHeight;
        const raw = scrollable > 0 ? el.scrollTop / scrollable : 0;
        const target = Math.max(0, Math.min(1, raw)) * video.duration;

        // Lerp: smooth interpolation toward target (12% per frame)
        currentRef.current = lerp(currentRef.current, target, 0.12);

        // Only seek if delta > 1 frame AND not already seeking
        const delta = Math.abs(currentRef.current - video.currentTime);
        if (delta > 0.04 && !seekingRef.current) {
          seekingRef.current = true;
          video.currentTime = currentRef.current;
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafRef.current);
    };
  }, [scrollContainerRef]);

  return (
    <div className="relative w-full h-full">
      <video
        ref={videoRef}
        src="/art-video.mp4"
        muted
        playsInline
        preload="auto"
        className="hidden"  // Hidden — canvas displays the frames
      />
      <canvas
        ref={canvasRef}
        className="w-full h-full object-cover"
      />
    </div>
  );
}
```

**Why canvas is better**:
- `ctx.drawImage(video, ...)` always draws the current decoded frame cleanly
- No flicker from incomplete seeks — the canvas only updates on `seeked` event
- The video element is `hidden` — it's just a frame source

### Lerp Interpolation

Direct `video.currentTime = progress * duration` is jarring — it jumps frame-to-frame. Linear interpolation smooths this:

```ts
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
// Each frame: current = lerp(current, target, 0.12)
// 0.12 = 12% toward target per frame → smooth glide
// Higher = snappier (0.3), Lower = floatier (0.05)
```

### Seek Gating

Browsers can only handle one seek at a time. Overlapping seeks cause stuttering:

```ts
const seekingRef = useRef(false);

video.addEventListener('seeked', () => {
  // ... draw to canvas ...
  seekingRef.current = false;  // Ready for next seek
});

// In tick():
if (delta > 0.04 && !seekingRef.current) {
  seekingRef.current = true;
  video.currentTime = currentRef.current;
}
```

- `delta > 0.04` = only seek if the difference exceeds ~1 frame at 24fps
- `!seekingRef.current` = wait for previous seek to complete

### Opacity Must Start at 1

**NEVER** set initial opacity based on scroll progress. If `opacity = progress * 3`, the video is invisible at the top of the page. The video should always be fully visible — only `currentTime` changes with scroll.
