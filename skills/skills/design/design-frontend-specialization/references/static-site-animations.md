# Static Site Animation Patterns (No Build Step)

Reliable animation techniques for vanilla HTML/CSS/JS sites deployed to Cloudflare Pages or similar static hosts.

## Why CSS-only over JS animation libraries?

JS animation libraries loaded via CDN ES modules (Motion, GSAP, etc.) can fail silently due to:
- Browser Content Security Policy (CSP)
- Ad blockers or privacy extensions
- Module loading race conditions
- Network failures on the CDN

CSS animations + vanilla JS canvas run 100% of the time.

## Pattern: Aurora Background (CSS)

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

## Pattern: Particle Network (Canvas)

```javascript
const canvas = document.createElement('canvas');
canvas.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:-1;opacity:.6';
document.body.appendChild(canvas);
const ctx = canvas.getContext('2d');

function resize() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener('resize', resize);
resize();

const particles = Array.from({ length: 60 }, () => ({
  x: Math.random() * canvas.width,
  y: Math.random() * canvas.height,
  vx: (Math.random() - .5) * .3,
  vy: (Math.random() - .5) * .3,
  r: Math.random() * 2 + .5,
  alpha: Math.random() * .5 + .2,
  color: Math.random() > .5 ? '139,92,246' : '6,182,212',
}));

function animate() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x;
      const dy = particles[i].y - particles[j].y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < 150) {
        ctx.beginPath();
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.strokeStyle = `rgba(139,92,246,${.08 * (1 - dist/150)})`;
        ctx.lineWidth = .5;
        ctx.stroke();
      }
    }
  }
  particles.forEach(p => {
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
    if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${p.color},${p.alpha})`;
    ctx.fill();
  });
  requestAnimationFrame(animate);
}
animate();
```

## Pattern: Scroll Reveal (IntersectionObserver)

```javascript
const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      Array.from(entry.target.children).forEach((child, idx) => {
        child.style.opacity = '0';
        child.style.transform = 'translateY(40px)';
        setTimeout(() => {
          child.style.transition = 'all .7s cubic-bezier(.16,1,.3,1)';
          child.style.opacity = '1';
          child.style.transform = 'translateY(0)';
        }, idx * 120);
      });
      observer.unobserve(entry.target);
    }
  });
}, { threshold: .1 });

document.querySelectorAll('.card-grid').forEach(el => observer.observe(el));
```

## Pattern: 3D Card Tilt (vanilla JS)

```javascript
document.querySelectorAll('.card').forEach(card => {
  card.addEventListener('mousemove', (e) => {
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const rx = (y - cy) / cy * -8;
    const ry = (x - cx) / cx * 8;
    card.style.transform = `perspective(800px) rotateX(${rx}deg) rotateY(${ry}deg) translateZ(10px)`;
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
    card.style.transition = 'transform .5s cubic-bezier(.16,1,.3,1)';
  });
});
```

## Pattern: Gradient Text Shimmer

```css
.gradient-text {
  background: linear-gradient(135deg, #fff 0%, #c4b5fd 40%, #22d3ee 70%, #fff 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: shimmer 4s ease-in-out infinite;
}
@keyframes shimmer {
  0%, 100% { background-position: 0% center; }
  50% { background-position: 100% center; }
}
```

## Pattern: Mouse-following Glow

```css
.cinema-card {
  --mouse-x: 50%;
  --mouse-y: 50%;
  position: relative;
}
.cinema-card::after {
  content: '';
  position: absolute; inset: 0;
  border-radius: inherit;
  background: radial-gradient(circle 300px at var(--mouse-x) var(--mouse-y), rgba(139,92,246,.15), transparent);
  pointer-events: none;
  opacity: 0;
  transition: opacity .3s;
}
.cinema-card:hover::after { opacity: 1; }
```

```javascript
cinema.addEventListener('mousemove', (e) => {
  const rect = cinema.getBoundingClientRect();
  cinema.style.setProperty('--mouse-x', `${((e.clientX - rect.left) / rect.width) * 100}%`);
  cinema.style.setProperty('--mouse-y', `${((e.clientY - rect.top) / rect.height) * 100}%`);
});
```

## Motion for Static HTML (Vanilla JS)

For static sites (Cloudflare Pages, vanilla HTML), Motion can be loaded via ESM CDN — no build step required.

### ESM CDN Import
```html
<script type="module">
import { animate, inView, spring } from "https://cdn.jsdelivr.net/npm/motion@12.0.0/+esm";
</script>
```

### Pattern V1: Scroll-triggered reveals
```html
<script type="module">
import { animate, inView, spring } from "https://cdn.jsdelivr.net/npm/motion@12.0.0/+esm";

inView('.page-hero', () => {
  animate('.page-hero > *', 
    { opacity: [0,1], y: [30,0] }, 
    { duration: 0.7, delay: (i) => i * 0.1, ease: spring({ stiffness: 100, damping: 20 }) }
  );
});

inView('.card-grid', () => {
  animate('.card-grid .card', 
    { opacity: [0,1], y: [40,0] }, 
    { duration: 0.6, delay: (i) => i * 0.12, ease: "easeOut" }
  );
});
</script>
```

### Pattern V2: Stagger helper for vanilla
```javascript
function stagger(delay) {
  return (i) => i * delay;
}
// Usage: { delay: stagger(0.1) }
```

---
