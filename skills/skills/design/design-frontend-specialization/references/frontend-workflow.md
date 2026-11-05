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
