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
