# Metallic Gold / Premium Effects CSS Reference

## Metallic Gold Palette (5 layers)
```css
:root {
  --gold-dark: #8b6914;   /* Deep shadow */
  --gold-mid: #b8860b;    /* Mid-tone */
  --gold-base: #d4af37;   /* Base gold */
  --gold-light: #f4d03f;  /* Highlight */
  --gold-bright: #ffd700; /* Bright accent */
}
```

## Metallic Gradients (not linear!)
Linear gradients look flat/yellow. Use these for true metallic feel:

### Radial gradient (sphere-like reflection)
```css
--gold-metallic: radial-gradient(
  ellipse at 30% 20%,           /* Light source top-left */
  #ffd700 0%,                   /* Bright highlight */
  #d4af37 25%,                  /* Base */
  #b8860b 50%,                  /* Mid */
  #8b6914 75%,                  /* Shadow */
  #6b4e0f 100%                  /* Deep shadow */
);
```

### Conic gradient (rotating reflection)
```css
--gold-metallic-2: conic-gradient(
  from 45deg at 50% 50%,
  #8b6914, #d4af37, #ffd700, #f4d03f, #d4af37, #8b6914
);
```

### Shine sweep (animated)
```css
--gold-shine: linear-gradient(
  135deg,
  transparent 30%,
  rgba(255,215,0,0.4) 50%,
  transparent 70%
);
```

## Metallic Depth Effects

### Inset shadows for relief (buttons, badges, numbers)
```css
box-shadow:
  0 8px 30px rgba(212,175,55,0.4),     /* Outer glow */
  inset 0 1px 0 rgba(255,255,255,0.3),  /* Top highlight */
  inset 0 -2px 4px rgba(0,0,0,0.3);     /* Bottom shadow */
```

### Text depth
```css
text-shadow: 0 1px 2px rgba(0,0,0,0.3);
```

### Light reflection overlay (pseudo-element)
```css
.element::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: radial-gradient(
    ellipse at 30% 20%,
    rgba(255,255,255,0.3) 0%,
    transparent 70%
  );
  pointer-events: none;
}
```

## Animated Effects

### Rotating shine on borders
```css
@keyframes rotate-shine {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.border-shine::before {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: inherit;
  background: conic-gradient(from 45deg, #8b6914, #d4af37, #ffd700, #f4d03f, #d4af37, #8b6914);
  z-index: -1;
  opacity: 0;
  transition: opacity 0.5s;
  animation: rotate-shine 4s linear infinite;
}
.border-shine:hover::before { opacity: 1; }
```

### Shimmer sweep on buttons
```css
@keyframes shimmer {
  0% { background-position: -1000px 0; }
  100% { background-position: 1000px 0; }
}

.btn-gold::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: var(--gold-shine);
  transition: left 0.5s;
}
.btn-gold:hover::before { left: 100%; }
```

## Anti-patterns (what NOT to do)
- `linear-gradient(#d4af37, #f4d03f)` → looks flat yellow, not metallic
- Single `background-color: gold` → no depth
- Missing `inset` shadows → buttons look painted on
- No light reflection pseudo-element → objects look 2D
- Using `#FFD700` alone → classic "yellow", not gold
