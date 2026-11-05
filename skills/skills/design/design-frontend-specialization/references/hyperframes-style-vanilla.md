# Hyperframes-style Vanilla Effects (Production Static Sites)

Reference: Scena redesign session 2026-05-09. User explicitly demanded hyperframes.dev / motion.dev / 21st.dev style and rejected vanilla glassmorphism. This is the aggressive vanilla fallback that was accepted.

## Effects Stack

### 1. Film Grain Overlay (CSS)
```css
body::before {
  content: '';
  position: fixed; inset: 0;
  pointer-events: none; z-index: 9999;
  opacity: .05;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  background-repeat: repeat;
  background-size: 256px 256px;
}
```

### 2. Scanlines (CSS)
```css
body::after {
  content: '';
  position: fixed; inset: 0;
  pointer-events: none; z-index: 9998;
  opacity: .04;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,.03) 2px, rgba(255,255,255,.03) 4px);
}
```

### 3. Gradient Text Shimmer (CSS animation)
```css
.gradient-text {
  background: linear-gradient(135deg, #fff 0%, #c4b5fd 35%, #22d3ee 70%, #a78bfa 100%);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: gradient-shift 5s ease infinite;
}
@keyframes gradient-shift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
```

### 4. Canvas Particle Network (vanilla JS)
Full implementation in `templates/hyperframes-effects.js`.

Key: 50 particles, connected with lines when distance < 150px, violet color theme. Runs in a `<canvas>` behind content.

### 5. Spotlight Mouse Tracking (CSS variables + JS)
```javascript
document.querySelectorAll('.spotlight-card, .card').forEach(el => {
  el.addEventListener('mousemove', (e) => {
    const rect = el.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    el.style.setProperty('--mouse-x', `${x}%`);
    el.style.setProperty('--mouse-y', `${y}%`);
  });
});
```

With CSS:
```css
.spotlight-card::before {
  content: '';
  position: absolute;
  top: var(--mouse-y, 50%);
  left: var(--mouse-x, 50%);
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(167,139,250,.15), transparent 60%);
  transform: translate(-50%, -50%);
  opacity: 0;
  transition: opacity .3s;
  pointer-events: none;
}
.spotlight-card:hover::before { opacity: 1; }
```

### 6. 3D Card Tilt (vanilla JS)
```javascript
document.querySelectorAll('.card').forEach(card => {
  card.addEventListener('mousemove', (e) => {
    const rect = card.getBoundingClientRect();
    const cx = rect.width / 2, cy = rect.height / 2;
    const rx = (e.clientY - rect.top - cy) / cy * -10;
    const ry = (e.clientX - rect.left - cx) / cx * 10;
    card.style.transform = `perspective(1000px) rotateX(${rx}deg) rotateY(${ry}deg) translateZ(20px)`;
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
    card.style.transition = 'transform .6s cubic-bezier(.16,1,.3,1)';
  });
});
```

### 7. Video Grid (hyperframes layout)
```css
.video-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  grid-template-rows: 1.2fr .8fr;
  gap: 10px;
}
.video-cell.large { grid-row: span 2; }
```

### 8. Staggered Scroll Reveal (IntersectionObserver + CSS)
Use `IntersectionObserver` to add `.visible` class that triggers `@keyframes fadeUp`.

## Full Template

See `templates/hyperframes-effects.js` for the complete vanilla JS file and `templates/hyperframes-style.css` for the complete CSS.

## User Preference: Atypical / Aggressive Visual Style

Lucas explicitly expects a **premium, atypical, animation-heavy** aesthetic when he references `hyperframes.dev`, `motion.dev`, or `21st.dev`. **Vanilla CSS glassmorphism cards + basic JS scroll reveals will be rejected.** He has demonstrated this multiple times — generic glassmorphism deployed three times in one session was rejected each time with "non c'est toujours pas terrible, je veux un style atypique".

**Preferred reference design**: `fakerich-ai.pages.dev` — dark theme with sophisticated gold palette, Playfair Display serif headings, rich visual imagery, and premium motion effects. This is the baseline aesthetic Lucas approves.

**Color palette sophistication matters:**
- **"Gold" ≠ yellow**. When user says "gold", use multi-layered metallic gradients: `#d4af37`, `#f4d03f`, `#ffd700`, `#b8860b`, `#daa520`
- Include shimmer animations, backdrop blur, dynamic shadows, and luminous borders
- Flat colors get rejected as "jaune" not "gold"
- Use gradient text effects: `background: linear-gradient(135deg, #d4af37, #f4d03f, #ffd700); -webkit-background-clip: text; -webkit-text-fill-color: transparent;`

**Visual richness requirements:**
- Hero sections need substantial imagery (AI-generated luxury photos work well)
- Use floating/infinite scroll galleries for showcasing work
- Include parallax effects, 3D transforms, and depth layers
- Stats and numbers should animate (count-up, float, or pulse)
- Cards need hover states with glow effects and border illumination

When these references appear, immediately assess:
- **React + Motion + GSAP** (preferred if env healthy): Vite + React + Motion + GSAP build with aggressive spring physics, layout animations, shared element transitions, scroll-driven timelines, and SVG effects
- **Vanilla aggressive fallback** (if Node/npm is broken): Canvas particles, film grain, scanlines, gradient text shimmer, 3D tilt, spotlight mouse tracking, typing effects, GSAP scroll-triggered sequences — not just hover shadows

**Critical rule: Do not iterate on subtle variations of the same design.** If Lucas rejects a design, pivot to a genuinely different aesthetic rather than tweaking the same glassmorphism. The atypical request means "not like every other SaaS landing page".

Do not deliver generic dark-mode SaaS templates. Lucas wants designs that feel like they came out of hyperframes.dev or 21st.dev — cinematic, textured, alive.

**Color palette sophistication matters:** When user says "gold" they mean multi-layered metallic gradients (#d4af37, #f4d03f, #ffd700, #b8860b, #daa520), not flat yellow (#d4af37 alone). Include shimmer animations, backdrop blur, dynamic shadows, and luminous borders. Flat colors get rejected as "jaune" not "gold".

**GSAP without premium plugins is basic.** Core GSAP tweens (`gsap.to`, `gsap.from`) alone will look "décevant" / disappointing to Lucas. The wow factor comes from premium plugins: `ScrollSmoother` (smooth inertial scroll), `SplitText` (character-level text reveals), `MorphSVG` (shape morphing), `DrawSVG` (stroke drawing), `ScrambleText` (decoding text), and `ScrollTrigger` pin/scrub. These require `npm install gsap` — they do NOT exist on public CDNs. See `gsap-frontend` skill for plugin setup and deployment patterns.

**If using vanilla HTML for Cloudflare Pages:** copy plugin files from `node_modules/gsap/dist/` — do not try to load `SplitText`, `ScrollSmoother`, `MorphSVGPlugin`, `DrawSVGPlugin`, or `ScrambleTextPlugin` from jsdelivr/unpkg (they 404).

### Motion vs GSAP — When to Use Which

Both libraries can coexist in the same project.

| Use Case | Library | Why |
|----------|---------|-----|
| React component enter/exit | **Motion** | `AnimatePresence`, declarative JSX, layout animations |
| Hover/tap micro-interactions | **Motion** | `whileHover`, `whileTap`, spring physics |
| Shared element transitions | **Motion** | `layoutId` magic move |
| Scroll-driven animations | **GSAP** | `ScrollTrigger` is the industry standard for pinning, scrub, complex scroll logic |
| Complex timelines | **GSAP** | Labels, nesting, precise sequencing, runtime control (play/pause/reverse/seek) |
| SVG morphing/drawing | **GSAP** | `MorphSVG`, `DrawSVG`, `MotionPath` plugins |
| Text effects | **GSAP** | `SplitText`, `ScrambleText` |
| FLIP layout transitions | **GSAP** | `Flip` plugin for complex DOM changes |
| Physics/draggable | **GSAP** | `Draggable`, `Inertia` plugins |

**Rule of thumb**: Motion for React UI layer animations; GSAP for scroll, timeline, SVG, text, and anything requiring runtime control.

For GSAP-specific patterns, load the **`gsap-frontend`** skill.

For video composition and rendering (HTML → MP4 via Puppeteer + FFmpeg), load the **`hyperframes-video-rendering`** skill. HyperFrames uses the same GSAP timeline patterns but renders to deterministic video files — perfect for Scena's post-generation pipeline.

---
