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
