# Hyperframes-Style Design Effects

Reference: extracted from hyperframes.dev, motion.dev, 21st.dev visual language.
Use when the user asks for "atypical", "modern", "design-forward", or specifically references these sites.

## Core Visual Language

- **Background**: pure black (`#000000`) — not dark gray, not navy
- **Borders**: very subtle, low-opacity white (`rgba(255,255,255,.08)`)
- **Surfaces**: barely-raised dark (`#0a0a0a`, `#111111`)
- **Accent**: soft violet (`#a78bfa`) + cyan (`#22d3ee`) sparingly
- **No gradients on backgrounds** — flat black with texture instead
- **Border radius**: tight (`8px–16px`) for UI, `999px` for pills only

## Texture Effects (CSS-only)

### Film Grain
```css
body::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9999;
  opacity: .035;
  background-image: url("data:image/svg+xml,...feTurbulence...");
  background-repeat: repeat;
  background-size: 256px 256px;
}
```

### Scanlines
```css
body::after {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9998;
  opacity: .03;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(255,255,255,.03) 2px,
    rgba(255,255,255,.03) 4px
  );
}
```

## Interactive Effects

### Spotlight Follow (mouse-tracking glow)
```css
.spotlight-card {
  position: relative;
  overflow: hidden;
}
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
```js
el.addEventListener('mousemove', (e) => {
  const rect = el.getBoundingClientRect();
  el.style.setProperty('--mouse-x', `${((e.clientX - rect.left) / rect.width) * 100}%`);
  el.style.setProperty('--mouse-y', `${((e.clientY - rect.top) / rect.height) * 100}%`);
});
```

### 3D Tilt (perspective card hover)
```js
const rx = (y - cy) / cy * -10;
const ry = (x - cx) / cx * 10;
el.style.transform = `perspective(1000px) rotateX(${rx}deg) rotateY(${ry}deg) translateZ(20px)`;
```
Reset on `mouseleave` with a slow transition.

### Video Grid (hyperframes layout)
```css
.video-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  grid-template-rows: 1.2fr .8fr;
  gap: 10px;
}
.video-cell.large { grid-row: span 2; }
```
Each cell: placeholder spinner + label badge + meta tags.

### Magnetic Buttons
```js
el.style.transform = `translate(${(e.clientX - rect.left - rect.width/2)*.15}px, ${(e.clientY - rect.top - rect.height/2)*.15}px)`;
```

### Gradient Text Shimmer
```css
.gradient-text {
  background: linear-gradient(135deg, #fff 0%, #c4b5fd 35%, #22d3ee 70%, #a78bfa 100%);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: gradient-shift 5s ease infinite;
}
```

### Typing Effect
Type character-by-character with a blinking cursor. Use a `<span class="typing-cursor">|</span>` with `animation: blink 1s step-end infinite`.

## Navigation Pattern

Floating pill nav, centered, `backdrop-filter: blur(40px)`, border-radius `999px`, NOT full-width sticky.

## Pitfalls

- **Do NOT use generic glassmorphism** — this style is deliberately flat, textured, and dark
- **Do NOT use aurora gradients** — pure black with grain/scanlines instead
- **Do NOT load Motion.dev ES modules** — they fail silently on static sites. Use CSS `@keyframes` + vanilla JS
- **Do NOT use rounded corners > 24px** — keep edges tight and precise
- **Verify visually before declaring done** — this style is subtle; screenshots or browser preview are essential
