---
name: design-frontend-specialization
category: multi-model-coder-router
description: Frontend design specialization for the coder profile — React + Tailwind + Motion (motion.dev) + GSAP + 21st.dev community components. Systematic workflow for building polished, animated UIs with complex timelines and scroll-driven effects.
tags: [design, frontend, react, motion, gsap, animation, tailwind, components, ui, ux]
---

# Design Frontend Specialization

## Purpose

Production-grade frontend design workflow for the `coder` profile. Leverages two primary resources:

1. **[Motion](https://motion.dev)** (ex-Framer Motion) — React animation library, 31.7k★ MIT. Hybrid engine: Web Animations API + JS fallback, 120fps GPU-accelerated.
2. **[21st.dev](https://21st.dev/community/components)** — Community marketplace of copy-paste React/Tailwind components.

**Stack default**: React 18+ / TypeScript / Tailwind CSS / Motion / GSAP / 21st components

### User Preference: Atypical / Aggressive Visual Style

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

## Workflow: Design Task Execution

### Phase 1 — Analyze (always first)

1. Parse the design task for:
   - **Component type** (landing page, dashboard, card, navbar, modal, form, hero, pricing table, etc.)
   - **Animation needs** (micro-interactions, page transitions, scroll effects, layout animations, gestures)
   - **Existing codebase** (check for Tailwind config, existing component patterns, design tokens)
2. Check the repo for `tailwind.config.ts`, design tokens, or existing component conventions.

### Phase 2 — Source Components (21st.dev first)

**Rule**: Never build a component from scratch if 21st.dev has an equivalent. The site returns 404 for direct API hits — it's a client-side rendered Next.js app. Browse it manually or use the sitemap structure:

| Page | URL |
|------|-----|
| Popular | `https://21st.dev/community/components/popular` |
| Newest | `https://21st.dev/community/components/newest` |
| Featured | `https://21st.dev/community/components/featured` |
| Themes | `https://21st.dev/community/themes` |

**How to search 21st.dev** (browser-based):
- Navigate to `https://21st.dev/community/components` and use the search bar
- Components are tagged by category (button, card, navbar, hero, form, modal, etc.)
- Each component shows copy-paste code with Tailwind classes
- Components are published by community members, open source

**Selection criteria**:
1. Matches the functional need
2. Uses Tailwind (consistent with stack)
3. Has good TypeScript types
4. Is well-maintained (recently updated, good reviews)
5. Minimal external dependencies beyond React + Tailwind

**Fallback**: If no suitable 21st component exists, build from scratch using Tailwind + Motion, following the component patterns below.

### Phase 3 — Add Motion Animations

Import: `import { motion } from "motion/react"` (NOT `framer-motion` — the old package name).

#### Pattern A: Fade-in on mount
```tsx
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.4, ease: "easeOut" }}
>
  {children}
</motion.div>
```

#### Pattern B: Scroll-triggered reveal
```tsx
<motion.div
  initial={{ opacity: 0, y: 40 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: "-100px" }}
  transition={{ duration: 0.5 }}
>
  {children}
</motion.div>
```

#### Pattern C: Stagger children
```tsx
<motion.div
  initial="hidden"
  animate="visible"
  variants={{
    hidden: {},
    visible: { transition: { staggerChildren: 0.1 } }
  }}
>
  {items.map((item, i) => (
    <motion.div
      key={i}
      variants={{
        hidden: { opacity: 0, y: 20 },
        visible: { opacity: 1, y: 0 }
      }}
    >
      {item}
    </motion.div>
  ))}
</motion.div>
```

#### Pattern D: Layout animations (auto-animate position/size changes)
```tsx
<motion.div layout>
  {/* Automatically animates when position/size changes */}
</motion.div>
```

#### Pattern E: Shared element transitions (magic move)
```tsx
// Component A
<motion.div layoutId="shared-element">
  <Thumbnail />
</motion.div>

// Component B (different parent)
<motion.div layoutId="shared-element">
  <FullImage />
</motion.div>
```

#### Pattern F: Hover/tap micro-interactions
```tsx
<motion.button
  whileHover={{ scale: 1.05 }}
  whileTap={{ scale: 0.95 }}
  transition={{ type: "spring", stiffness: 400, damping: 17 }}
>
  Click me
</motion.button>
```

#### Pattern G: AnimatePresence (exit animations)
```tsx
<AnimatePresence>
  {isVisible && (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.2 }}
    >
      {children}
    </motion.div>
  )}
</AnimatePresence>
```

#### Pattern H: Scroll-linked (parallax, progress)
```tsx
import { useScroll, useTransform, motion } from "motion/react"

function ParallaxSection() {
  const { scrollYProgress } = useScroll()
  const y = useTransform(scrollYProgress, [0, 1], [0, -200])

  return <motion.div style={{ y }}>Parallax content</motion.div>
}
```

#### Pattern I: Spring-based value animations
```tsx
<motion.div
  animate={{ x: 100 }}
  transition={{
    type: "spring",
    stiffness: 300,
    damping: 20,
    mass: 1
  }}
/>
```

### Phase 4 — Polish & Integrate

1. **Tailwind consistency**: Ensure 21st components use the same Tailwind theme (colors, spacing, fonts). Override with the repo's `tailwind.config` tokens.
2. **Dark mode**: All components must support dark mode via Tailwind `dark:` prefix.
3. **Responsive**: Test breakpoints (sm/md/lg/xl) — 21st components often come responsive-ready.
4. **Accessibility**: Ensure `aria-*` attributes, keyboard navigation, `prefers-reduced-motion` support:
   ```tsx
   import { useReducedMotion } from "motion/react"

   const prefersReduced = useReducedMotion()
   const animationProps = prefersReduced ? {} : { animate: { opacity: 1 } }
   ```
5. **TypeScript**: All components must have proper prop types.

### Phase 5 — Verify

```bash
# Type check
npx tsc --noEmit

# Lint
npx eslint . --ext .tsx,.ts

# Build check
npm run build 2>&1 | tail -20

# Visual check (if browser available)
# Navigate to the component and verify animations are smooth
```

### Phase 6 — Review gate before production deploy

For Lucas/Scena public-facing sites, **do not push/deploy the redesigned site straight to production without a visual review checkpoint**. Build the multi-page site locally or in a preview artifact, run a browser/visual smoke, capture screenshots or a preview URL, and ask Lucas for design feedback before Cloudflare Pages production deploy. Backend/API hardening can be deployed after tests, but public web design changes need review first.

**Exception**: If Lucas explicitly says "bon push en prod" or similar direct deploy command after reviewing, deploy immediately without further confirmation.

---

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

## Component Categories & Quick Patterns

### Landing Page
- **Hero**: 21st search "hero" → copy, add Pattern A + scroll indicator with Pattern H
- **Features grid**: Stagger cards (Pattern C) on scroll (Pattern B)
- **CTA section**: Pattern B + button hover (Pattern F)
- **Footer**: 21st search "footer" → static, no animation needed
- **Scroll-driven sections**: Use GSAP ScrollTrigger for pinned hero, parallax images, or scrubbed progress animations (see `gsap-frontend` skill)
- **Auth modal**: Use a floating modal instead of separate login/signup pages. Pattern: fixed overlay with backdrop blur, animated entrance (Pattern G), tabs for switching between login/signup, close on backdrop click or ESC key. Keeps users on the landing page flow.

### Auth Modal Pattern (Vanilla JS)
```html
<div class="auth-modal" id="authModal">
  <div class="auth-card">
    <button class="auth-close" onclick="closeAuthModal()">×</button>
    <div class="auth-tabs">
      <button class="auth-tab active" onclick="switchAuthTab('login')">Connexion</button>
      <button class="auth-tab" onclick="switchAuthTab('signup')">Inscription</button>
    </div>
    <form class="auth-form active" id="loginForm">...</form>
    <form class="auth-form" id="signupForm">...</form>
  </div>
</div>
```

```css
.auth-modal {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: none;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(10px);
}
.auth-modal.active {
  display: flex;
  animation: fadeIn 0.3s ease;
}
.auth-card {
  background: var(--surface);
  border: 1px solid var(--gold);
  border-radius: 20px;
  padding: 2rem;
  max-width: 400px;
  width: 90%;
  position: relative;
  animation: slideUp 0.3s ease;
}
```

```javascript
function openAuthModal(tab = 'login') {
  document.getElementById('authModal').classList.add('active');
  switchAuthTab(tab);
  document.body.style.overflow = 'hidden';
}

function closeAuthModal() {
  document.getElementById('authModal').classList.remove('active');
  document.body.style.overflow = '';
}

function switchAuthTab(tab) {
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
  
  if (tab === 'login') {
    document.querySelector('.auth-tab:first-child').classList.add('active');
    document.getElementById('loginForm').classList.add('active');
  } else {
    document.querySelector('.auth-tab:last-child').classList.add('active');
    document.getElementById('signupForm').classList.add('active');
  }
}

// Close on backdrop click
document.getElementById('authModal').addEventListener('click', (e) => {
  if (e.target.id === 'authModal') closeAuthModal();
});

// Close on ESC
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeAuthModal();
});
```

**User preference**: Lucas prefers modals over separate pages for auth flows on landing pages. Keeps the user in context and feels more modern.

### Dashboard
- **Sidebar**: 21st search "sidebar" → add layout animations for collapse (Pattern D)
- **Cards/Stats**: 21st search "card" or "stat" → stagger entrance (Pattern C)
- **Tables**: 21st search "table" → row hover highlight (Pattern F)
- **Charts area**: Pattern B entrance, keep charts static for readability
- **Scroll-based data viz**: GSAP ScrollTrigger for scrolling dashboards or horizontal scroll galleries

### Forms
- **Input groups**: 21st search "input" or "form" → add focus animations
- **Validation**: AnimatePresence for error messages (Pattern G)
- **Submit button**: Loading state with layout animation (Pattern D)

### Navigation
- **Navbar**: 21st search "navbar" or "header" → add scroll-aware background (Pattern H)
- **Mobile menu**: AnimatePresence for slide-in (Pattern G)
- **Dropdowns**: Pattern G with scale origin

---

## Motion Key APIs Reference

| API | Use case | Import |
|-----|----------|--------|
| `motion.div` | Wrap any HTML element for animation | `motion/react` |
| `animate` | Define animation target | prop on motion component |
| `initial` | Starting state (before mount) | prop on motion component |
| `exit` | State when removed from DOM | prop on motion component |
| `whileHover` | Hover animation target | prop on motion component |
| `whileTap` | Tap/click animation target | prop on motion component |
| `whileInView` | Trigger when scrolled into view | prop on motion component |
| `layout` | Auto-animate layout changes | prop on motion component |
| `layoutId` | Shared element across components | prop on motion component |
| `AnimatePresence` | Orchestrate exit animations | `motion/react` |
| `useScroll` | Get scroll progress (0→1) | `motion/react` |
| `useTransform` | Map value to output range | `motion/react` |
| `useSpring` | Spring physics on any value | `motion/react` |
| `useInView` | Detect if element is in viewport | `motion/react` |
| `useReducedMotion` | Respect accessibility preference | `motion/react` |
| `useDragControls` | Programmatic drag control | `motion/react` |
| `staggerChildren` | Delay between child animations | `variants` config |
| `transition` | Timing config (duration, ease, spring) | prop on motion component |
| `viewport` | Scroll trigger config (once, margin) | prop on motion component |

---

## Integration: Motion + 21st.dev

**Standard pattern** — wrap a 21st.dev component in a motion wrapper:

```tsx
import { motion } from "motion/react"
// 21st component (copy-pasted or imported)
import { FeatureCard } from "@/components/feature-card"

function AnimatedFeatureCard(props: FeatureCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4 }}
    >
      <FeatureCard {...props} />
    </motion.div>
  )
}
```

**For 21st components that already use `ref`** — use `motion.create()` to convert:

```tsx
const MotionFeatureCard = motion.create(FeatureCard)

function AnimatedFeatureCard(props: FeatureCardProps) {
  return (
    <MotionFeatureCard
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      {...props}
    />
  )
}
```

---

## Quick Start: New Frontend Project

```bash
# Create React + TypeScript + Tailwind project
npm create vite@latest my-app -- --template react-ts
cd my-app
npm install motion tailwindcss @tailwindcss/vite
npm install gsap @gsap/react
npm install -D @types/react

# Configure Tailwind (Vite plugin in vite.config.ts):
# import tailwindcss from '@tailwindcss/vite'
# plugins: [tailwindcss()]

# Add to index.css:
# @import "tailwindcss";

# Register GSAP plugins once in your app entry (e.g. main.tsx):
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
gsap.registerPlugin(ScrollTrigger);
```

---

## Design Tokens Convention

When building for an existing project, extract design tokens first:

```bash
# Find Tailwind config
find . -name "tailwind.config.*" -o -name "tailwind.css" | head -5

# Check for design system files
find . -name "*.css" -path "*/tokens/*" -o -name "design-tokens*" | head -5
```

Key tokens to extract:
- Colors (primary, secondary, accent, neutral)
- Font families
- Border radius
- Spacing scale
- Breakpoints

---

## FIRST LOADING RULE

**ALWAYS load this skill FIRST when the user asks for ANY landing page, frontend, website redesign, or design work.** Do NOT start building HTML/CSS/JS before loading this skill and the companion `gsap-frontend` skill. The agent has been caught multiple times defaulting to vanilla HTML/CSS with basic IntersectionObserver scroll reveals — this is the WRONG approach for this user. The user expects the full animation stack (GSAP premium plugins, Motion, 21st.dev components) to be in play from the first line of code.

**Workflow for landing pages / frontend redesign:**
1. Load `design-frontend-specialization` (this skill)
2. Load `gsap-frontend` (for premium GSAP plugins)
3. Load `popular-web-designs` if brand/style references are needed
4. Load `cloudflare-pages-deploy` for deployment patterns
5. THEN start building

Do NOT skip steps 1-4. Building vanilla HTML first and "adding animations later" wastes entire iterations and will be rejected.

## Pitfalls

- **Do NOT `npm install framer-motion`** — the package was renamed to `motion`. Use `npm install motion` and import from `motion/react`.
- **21st.dev has no public REST API** — the site is a client-side Next.js app with tRPC. Browse it, don't curl it.
- **Don't over-animate** — every animation must serve UX purpose: guide attention, provide feedback, or create continuity. If it's purely decorative, it slows down the user.
- **Avoid layout shift** — set explicit dimensions on elements that will animate in. Motion's `layout` prop measures element size, but initial render must not cause CLS.
- **`AnimatePresence` needs keys** — each child must have a unique `key` prop, otherwise exit animations won't fire.
- **Don't mix `framer-motion` v11 and `motion` v12** — they conflict. Use only `motion`.
- **Motion ESM CDN works for vanilla HTML** — use `https://cdn.jsdelivr.net/npm/motion@12.0.0/+esm` with `import { animate, inView, spring }`. No build step needed for static sites.
- **Cache busting after deploy** — Cloudflare Pages serves static assets with `cache-control: max-age=14400` (4 hours). After deploying design changes, users will see stale CSS/JS unless they hard-refresh. Always append version query params to assets (`style.css?v=2`) or tell users to Ctrl+Shift+R. **Always verify the deployed file content via `curl` before telling the user it's live** — don't trust browser previews alone.
- **When user explicitly references hyperframes.dev / motion.dev / 21st.dev — do NOT deliver vanilla CSS basics** — These references signal the user expects a *premium, atypical, animation-heavy* aesthetic. Vanilla CSS glassmorphism cards + basic JS scroll reveals will be rejected. Immediately ask: "React + Motion build, or aggressive vanilla canvas/CSS?" If React: scaffold Vite+React+Motion properly first (check Node/npm availability, install deps cleanly). If vanilla: commit to canvas particles, film grain, scanlines, gradient text shimmer, 3D tilt, spotlight tracking — not just hover shadows.
- **Don't attempt React+Vite scaffolding mid-session without env check** — If the environment lacks Node 18+, has broken npm, or tsc issues, a React build will fail repeatedly and waste turns. Check `node --version && npm --version` first. If the env is fragile, stick to vanilla with aggressive effects rather than fighting the build system.
- **Vanilla JS auth modals need CSS preserved across redesigns** — When redesigning a static site, auth modal styles (`#sign-in-modal`, `.dashboard`, `.stats`, `.credit-plans`, `.bot-setup`) are easy to accidentally delete. Always grep for `hidden` class usage and modal/dashboard CSS before declaring a redesign complete. A missing modal CSS rule makes the modal "display" but invisible (no position/fixed/overlay styles), causing the auth flow to appear broken when it's actually a CSS omission.
- **Scroll animations on mobile** — test `whileInView` on real mobile viewports. Use `viewport={{ once: true, margin: "-50px" }}` to trigger earlier.
- **Bundle size** — `motion` is tree-shakeable (~35KB gzipped). Import only what you use. For vanilla HTML CDN, the browser loads only used modules via ESM.
- **GSAP premium plugins 404 on public CDNs** — `SplitText`, `ScrollSmoother`, `MorphSVGPlugin`, `DrawSVGPlugin`, `ScrambleTextPlugin` do not exist on jsdelivr/unpkg. For vanilla HTML deploys, install `gsap` via npm and copy files from `node_modules/gsap/dist/` locally. See `gsap-frontend` skill.
- **GSAP without premium plugins looks basic** — if Lucas calls animations "décevantes", you are likely using only core tweens. Add SplitText, ScrollSmoother, MorphSVG, or DrawSVG for the cinematic effect he expects.
- **ScrambleTextPlugin destroys HTML markup** — see `gsap-frontend` skill pitfalls. Never use scrambleText on elements containing `<br>`, `<span>`, or any inline tags — it strips them and renders raw HTML as visible text. Use `opacity + y` entrance or SplitText instead.
- **Vision models cannot reliably evaluate dark-theme contrast** — when building dark-mode UIs (bg #03040c, cards #1a2138), the vision model will repeatedly rate contrast as 1-2/10 even when WCAG AA contrast ratios are mathematically adequate (verified via `getComputedStyle` RGB comparison). **Do NOT iterate on contrast adjustments based solely on vision model feedback for dark themes.** Instead, verify contrast programmatically: extract `window.getComputedStyle(el).backgroundColor` and `color` via Playwright `page.evaluate()`, compute the relative luminance ratio, and trust the numbers. If the ratio is ≥ 4.5:1 (AA) or ≥ 7:1 (AAA), the contrast is fine — the vision model is wrong. Only adjust if the numerical ratio actually fails. This pitfall caused 5 unnecessary contrast-adjustment iterations in one session, each making the card background progressively lighter without the vision model ever acknowledging improvement.

---

## Linked Files

- `references/21st-dev-guide.md` — Browsing strategy for 21st.dev (no REST API)
- `references/static-site-animations.md` — Motion vanilla ESM CDN patterns for static HTML
- `references/dark-premium-design-system.md` — Aurora, glassmorphism, gradient border tokens
- `references/hyperframes-style-vanilla.md` — Session notes: when user demands hyperframes.dev/motion.dev/21st.dev style, aggressive vanilla fallback with canvas particles, film grain, scanlines, spotlight tracking, 3D tilt
- `references/scena-landing-v2-redesign-jun-2026.md` — Scena landing V2 redesign: icy/electric palette shift, terminal hero demo, canvas particles, GSAP premium, ScrambleTextPlugin HTML pitfall, vision model dark-theme contrast pitfall, dark theme contrast starting point, verification workflow
- `templates/hyperframes-vanilla-effects.js` — Complete vanilla JS effects engine (particles, spotlight, 3D tilt, stagger, typing) — zero deps, drop-in for static sites
- `templates/hyperframes-style.css` — Complete CSS design system (film grain, scanlines, gradient text, video grid, cards)
- `references/gsap-quick-reference.md` — GSAP API quick reference (linked from `gsap-frontend` skill)
- `references/gsap-cdn-plugin-availability.md` — Which GSAP plugins exist on public CDNs vs npm-only

The coder profile automatically routes design tasks to **Gemini 2.5 Pro** when trigger keywords are detected:

```
ui, ux, design, layout, landing page, css, frontend, component, wireframe, visual
```

This skill should be loaded **in addition** to the automatic route — it provides the concrete patterns and workflow, while Gemini 2.5 Pro brings the visual reasoning.

---

## Verification Checklist

After implementing a frontend task, verify:

- [ ] TypeScript compiles without errors (`npx tsc --noEmit`)
- [ ] Tailwind classes resolve (no broken/dangling classes)
- [ ] Dark mode renders correctly
- [ ] Responsive at 3 breakpoints (mobile / tablet / desktop)
- [ ] Animations respect `prefers-reduced-motion`
- [ ] No console errors on mount
- [ ] No layout shift during animation (CLS = 0)
- [ ] `AnimatePresence` children have unique `key` props
- [ ] Imports use `motion/react`, NOT `framer-motion`
