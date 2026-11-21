---
name: animated-backgrounds
category: creative
description: "Layered CSS + Canvas animated hero backgrounds — gradient orbs, particle constellation, aurora waves. Premium alternative to video backgrounds."
version: 1.0.0
metadata:
  hermes:
    tags: [animation, css, canvas, hero, landing-page, motion, background]
    related_skills: [claude-design, popular-web-designs]
---

# Animated Backgrounds Without Video

When the brief calls for a dynamic hero background and video is unavailable, heavy, or unwanted, use layered CSS + Canvas animations. Produces a premium cinematic feel without media files.

## Three-Layer Stack

### Layer 1: Gradient Orbs (CSS-only)

Large blurred radial-gradient circles that drift slowly via CSS keyframes. Each orb uses a different color, size, drift path, and duration.

```tsx
function GradientOrbs() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      <div
        className="absolute w-[600px] h-[600px] sm:w-[800px] sm:h-[800px] rounded-full opacity-20 animate-orb-1"
        style={{
          background: 'radial-gradient(circle, #7c3aed 0%, #2563eb 40%, transparent 70%)',
          filter: 'blur(80px)',
          top: '-15%', left: '-10%',
        }}
      />
      {/* 2-3 more orbs with different colors, positions, durations */}
    </div>
  )
}
```

Rules:
- **3-4 orbs max** — more creates visual noise, not depth
- **Blur 60-100px** — below 60px edges visible; above 100px color washes out
- **Opacity 0.06-0.20** — subtle is premium; too high looks like a gradient
- **Different durations** (15-25s) — prevents lockstep drift
- **Different drift paths** — each keyframe moves differently
- **Scale variation** (0.95-1.08) adds organic breathing

```css
@keyframes orb-drift-1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25%      { transform: translate(80px, 40px) scale(1.05); }
  50%      { transform: translate(30px, 80px) scale(0.95); }
  75%      { transform: translate(-40px, 30px) scale(1.02); }
}
```

### Layer 2: Particle Constellation (Canvas)

`<canvas>` rendering floating particles connected by proximity lines. Texture and depth.

```tsx
function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current!
    const ctx = canvas.getContext('2d')!
    const particles: {x:number; y:number; vx:number; vy:number; size:number}[] = []
    const PARTICLE_COUNT = 60
    const MAX_DIST = 120
    // resize handler, init random position + velocity
    // draw loop: move, bounce off edges, draw dots, draw lines between close particles
    // line alpha = (1 - dist/MAX_DIST) * 0.12
  }, [])
  return <canvas ref={canvasRef} className="absolute inset-0 z-[1] pointer-events-none opacity-50" />
}
```

Rules:
- **40-80 particles** — fewer looks empty, more hurts mobile perf
- **Connection distance 100-150px** — too short = invisible; too long = mesh net
- **Speed 0.2-0.5** — barely perceptible
- **Line alpha 0.08-0.15** — barely visible connections
- **Particle opacity 0.20-0.35** — subtle dots
- **Bounce edges** not wrap — wrapping creates discontinuity
- **Resize handler** — canvas must track viewport

### Layer 3: Aurora Waves (CSS)

Flowing gradient bands at viewport bottom for color warmth.

```tsx
function AuroraWaves() {
  return (
    <div className="absolute bottom-0 left-0 right-0 h-[40vh] pointer-events-none overflow-hidden z-[2]">
      <div
        className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[200%] h-full animate-aurora-1 opacity-[0.07]"
        style={{
          background: 'radial-gradient(ellipse at 50% 100%, #7c3aed 0%, transparent 60%)',
          filter: 'blur(60px)',
        }}
      />
    </div>
  )
}
```

## Composition Order

```
div.relative.w-full.h-screen.overflow-hidden.bg-black
  GradientOrbs          // z-0 color foundation
  ParticleField         // z-1 texture
  AuroraWaves           // z-2 bottom warmth
  div.bg-black/40       // z-10 dark overlay (CRITICAL — without it orbs wash out content)
  // Grain, spotlight, content at z-20+
```

## Complementary Overlays (Optional)

- **Grain** — SVG noise at opacity 0.03-0.05, animated with `steps()` for film-grain
- **Mouse spotlight** — `radial-gradient(600px circle at mouseX mouseY, rgba(255,255,255,0.04), transparent 60%)`
- **Corner accents** — thin gradient lines at viewport corners, fade-up animated
- **Scrolling marquee** — very low opacity brand text scrolling horizontally

## Performance

- Canvas: 60fps with 60 particles on modern devices
- CSS `filter: blur()` is GPU-accelerated — safe for 3-4 elements
- Avoid animating `filter` — animate `transform` instead
- Mobile: reduce `PARTICLE_COUNT` to 30-40 via `window.innerWidth` check
- `requestAnimationFrame` for canvas; CSS animations for everything else

## Video Background Sourcing (When Brief Calls for Video)

When the user explicitly wants a `<video>` background, source free stock videos from Mixkit (no watermark, 1080p, direct MP4 URLs).

### Mixkit URL Pattern

```
https://assets.mixkit.co/videos/{id}/{id}-1080.mp4
```

### Proven Video IDs (Dark/Cinematic, June 2026)

| ID | Description | Vibe |
|----|------------|------|
| 1963 | Metallic confetti bokeh on black | Premium, luxury |
| 40211 | Smoke forms moving | Moody, atmospheric |
| 1960 | Dark smoke | Cinematic, mysterious |
| 1964 | Smoke wisps | Ethereal, light |
| 470 | Ink flow in water | Artistic, fluid |
| 469 | Ink swirl | Organic, mesmerizing |
| 30717 | Grayscale abstract | Clean, minimal |
| 45298 | Flowing blue abstract | Tech, digital |

### How to Extract URLs from Mixkit Pages

```bash
curl -s 'https://mixkit.co/free-stock-video/abstract-background/' \
  -H 'User-Agent: Mozilla/5.0' \
  | grep -oP 'https://assets\.mixkit\.co/videos/[^"]*\.mp4' | head -10
```

### Video Element Pattern (React)

```tsx
<video
  autoPlay muted loop playsInline
  className="absolute inset-0 w-full h-full object-cover"
  src="https://assets.mixkit.co/videos/1963/1963-1080.mp4"
/>
```

Always add a dark overlay (`bg-black/40` to `bg-black/60`) above the video so text remains readable.

## When NOT To Use

- User explicitly wants video → source from Mixkit (see above) or use `<video>` with `object-cover`
- Very dark content needing maximum contrast → orbs add color that fights dark text
- Minimalist/monochrome brief → use particles-only or skip entirely
- Performance-critical (embedded, low-end) → CSS-only without canvas

## Scroll-Driven Video

The former top-level `scroll-driven-video` skill is absorbed here as a motion-background branch. When the brief calls for a video that plays forward as the user scrolls (parallax video), see `references/scroll-driven-video.md` for the full pattern: sticky video + scroll progress hook + scale transform. Combines well with Mixkit video sources above.

## lucide-react Pitfalls

Social media icons (`Instagram`, `Twitter`, `Facebook`) don't exist in many lucide-react versions. See `references/lucide-react-pitfalls.md` for safe alternatives and verification commands.
