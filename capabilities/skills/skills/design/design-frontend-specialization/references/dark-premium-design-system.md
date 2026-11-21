# Dark Premium Design System (Aurora + Glassmorphism)

Reference design system extracted from Scena landing page redesign (May 2026). Used for Lucas/Scena and similar dark-mode SaaS products.

## Design Tokens

```css
:root {
  color-scheme: dark;
  --bg: #030305;
  --bg-2: #0a0a0f;
  --surface: rgba(255,255,255,.03);
  --surface-hover: rgba(255,255,255,.06);
  --glass: rgba(255,255,255,.04);
  --glass-strong: rgba(255,255,255,.08);
  --line: rgba(255,255,255,.06);
  --line-strong: rgba(255,255,255,.12);
  --text: #f0f0f5;
  --text-dim: #a0a0b0;
  --text-faint: #606070;
  --accent: #8b5cf6;       /* violet */
  --accent-2: #06b6d4;     /* cyan */
  --accent-3: #f472b6;     /* pink */
  --accent-glow: rgba(139,92,246,.35);
  --accent-2-glow: rgba(6,182,212,.25);
  --green: #34d399;
  --red: #f87171;
  --warn: #fbbf24;
  --radius-sm: 12px;
  --radius: 20px;
  --radius-lg: 32px;
  --shadow: 0 25px 80px rgba(0,0,0,.5);
  --shadow-glow: 0 0 60px rgba(139,92,246,.15);
  --font: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}
```

## Full CSS Pattern

See `templates/dark-premium-site.css` for the complete stylesheet.

## Key Techniques

### Aurora Background
- 3 layered radial gradients (violet, cyan, pink)
- 20s infinite alternate animation
- `position: fixed` with `pointer-events: none`

### Grid Overlay
- 80px grid with `rgba(255,255,255,.015)` lines
- `mask-image` fade to transparent at bottom

### Gradient Borders
- `::before` pseudo-element with `padding: 1px`
- `mask-composite: exclude` to create border-only effect
- Works on any element with `position: relative`

### Glassmorphism Cards
- `background: var(--surface)` + `border: 1px solid var(--line)`
- Top gradient line (::before) appears on hover
- `transform: translateY(-4px)` + shadow on hover

### Magnetic Buttons
- Mousemove listener calculates offset from center
- `transform: translate(x*0.1, y*0.1)`
- Reset on mouseleave

## Motion Integration

```html
<script type="module">
import { animate, inView, spring } from "https://cdn.jsdelivr.net/npm/motion@12.0.0/+esm";

inView('.hero', () => {
  animate('.hero-content', { opacity: [0,1], y: [40,0] }, { duration: 0.8, ease: spring({ stiffness: 100, damping: 20 }) });
  animate('.hero-visual', { opacity: [0,1], scale: [0.95,1] }, { duration: 1, delay: 0.2 });
});
</script>
```

## Responsive Breakpoints

- `980px`: Grid switches to single column
- `760px`: Mobile nav toggle appears

## Accessibility

- `prefers-reduced-motion: reduce` disables all animations
- Aurora animation stops, transitions become instant

## Design Patterns: Aurora + Glassmorphism

Modern dark-mode premium aesthetic used for Scena and similar SaaS landing pages.

### Aurora Background (CSS-only)
```css
body::before {
  content: '';
  position: fixed; inset: 0;
  pointer-events: none; z-index: -2;
  background:
    radial-gradient(ellipse 80% 50% at 20% 40%, rgba(139,92,246,.15), transparent),
    radial-gradient(ellipse 60% 40% at 80% 60%, rgba(6,182,212,.1), transparent),
    radial-gradient(ellipse 50% 30% at 50% 0%, rgba(244,114,182,.08), transparent);
  animation: aurora 20s ease-in-out infinite alternate;
}
@keyframes aurora {
  0% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(2%, -1%) scale(1.02); }
  66% { transform: translate(-1%, 2%) scale(0.98); }
  100% { transform: translate(1%, -2%) scale(1.01); }
}
```

### Gradient Border (pseudo-element mask)
```css
.card-featured {
  position: relative;
  border-radius: 20px;
  background: rgba(255,255,255,.03);
}
.card-featured::before {
  content: '';
  position: absolute; inset: -1px;
  border-radius: 20px;
  padding: 1px;
  background: linear-gradient(135deg, rgba(139,92,246,.4), rgba(6,182,212,.2), transparent 60%);
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}
```

### Glassmorphism Nav
```css
.nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  background: rgba(3,3,5,.7);
  border-bottom: 1px solid rgba(255,255,255,.06);
  backdrop-filter: blur(32px) saturate(140%);
  -webkit-backdrop-filter: blur(32px) saturate(140%);
}
```

### Magnetic Hover (vanilla JS)
```javascript
document.querySelectorAll('.btn').forEach(btn => {
  btn.addEventListener('mousemove', (e) => {
    const rect = btn.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    btn.style.transform = `translate(${x * 0.1}px, ${y * 0.1}px)`;
  });
  btn.addEventListener('mouseleave', () => {
    btn.style.transform = '';
  });
});
```

### Text Gradient
```css
.gradient-text {
  background: linear-gradient(135deg, #fff 0%, #c4b5fd 40%, var(--accent-2) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
```

---
