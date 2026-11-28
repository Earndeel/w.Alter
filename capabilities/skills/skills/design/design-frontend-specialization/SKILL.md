---
name: design-frontend-specialization
category: multi-model-coder-router
description: Frontend design specialization for the coder profile — React + Tailwind + Motion (motion.dev) + GSAP + 21st.dev community components. Systematic workflow for building polished, animated UIs with complex timelines and scroll-driven effects.
tags: [design, frontend, react, motion, gsap, animation, tailwind, components, ui, ux]
---

# Design Frontend Specialization

## Always-on rules

**ALWAYS load this skill FIRST when the user asks for ANY landing page, frontend, website redesign, or design work.** Do NOT start building HTML/CSS/JS before loading this skill and the companion `gsap-frontend` skill.
Load `popular-web-designs` if brand/style references are needed.
Load `cloudflare-pages-deploy` for deployment patterns.

Lucas explicitly expects a **premium, atypical, animation-heavy** aesthetic when he references `hyperframes.dev`, `motion.dev`, or `21st.dev`.
**Critical rule: Do not iterate on subtle variations of the same design.** If Lucas rejects a design, pivot to a genuinely different aesthetic rather than tweaking the same glassmorphism.
Do not deliver generic dark-mode SaaS templates.

When building for an existing project, extract design tokens first.
Check the repo for `tailwind.config.ts`, design tokens, or existing component conventions.
Never build a component from scratch if 21st.dev has an equivalent.
**21st.dev has no public REST API** — the site is a client-side Next.js app with tRPC. Browse it, don't curl it.
Check `node --version && npm --version` first.
Use `npm install motion` and import from `motion/react`.
**Rule of thumb**: Motion for React UI layer animations; GSAP for scroll, timeline, SVG, text, and anything requiring runtime control.
For GSAP-specific patterns, load the **`gsap-frontend`** skill.

All components must support dark mode via Tailwind `dark:` prefix.
Test breakpoints (sm/md/lg/xl).
Ensure `aria-*` attributes, keyboard navigation, `prefers-reduced-motion` support.
All components must have proper prop types.
Every animation must serve UX purpose: guide attention, provide feedback, or create continuity.
Set explicit dimensions on elements that will animate in.

For Lucas/Scena public-facing sites, **do not push/deploy the redesigned site straight to production without a visual review checkpoint**.
Build the multi-page site locally or in a preview artifact, run a browser/visual smoke, capture screenshots or a preview URL, and ask Lucas for design feedback before Cloudflare Pages production deploy.
**Exception**: If Lucas explicitly says "bon push en prod" or similar direct deploy command after reviewing, deploy immediately without further confirmation.
**Always verify the deployed file content via `curl` before telling the user it's live**.
**Do NOT iterate on contrast adjustments based solely on vision model feedback for dark themes.**

## Purpose

Production-grade frontend design workflow for the `coder` profile. Leverages two primary resources:

1. **[Motion](https://motion.dev)** (ex-Framer Motion) — React animation library, 31.7k★ MIT. Hybrid engine: Web Animations API + JS fallback, 120fps GPU-accelerated.
2. **[21st.dev](https://21st.dev/community/components)** — Community marketplace of copy-paste React/Tailwind components.

**Stack default**: React 18+ / TypeScript / Tailwind CSS / Motion / GSAP / 21st components

### User Preference: Atypical / Aggressive Visual Style

## References (read with skill_read(name, file_path=...))

- `references/21st-dev-guide.md` — Read when searching, browsing, or obtaining components from 21st.dev.
- `references/dark-premium-design-system.md` — Read when implementing aurora backgrounds, glassmorphism, gradient borders, or premium dark-theme tokens.
- `references/frontend-pitfalls.md` — Read before implementation and deployment checks for dependency, animation, modal, CDN, caching, and contrast pitfalls.
- `references/frontend-workflow.md` — Read before executing a frontend task for analysis, sourcing, integration, design-token extraction, verification, and production review steps.
- `references/hyperframes-style-vanilla.md` — Read when choosing Lucas's visual direction, responding to rejected designs, comparing Motion with GSAP, or implementing an aggressive vanilla fallback.
- `references/motion-recipes.tsx` — Read when selecting reusable React Motion animation recipes.
- `references/react-motion-patterns.md` — Read when scaffolding a React frontend or implementing component categories, Motion APIs, and 21st.dev integration.
- `references/resource-directory.md` — Read when locating supporting references, vanilla templates, companion GSAP resources, or coder routing context.
- `references/scena-landing-v2-redesign-jun-2026.md` — Read for Scena redesign precedents, terminal heroes, premium GSAP effects, and dark-theme verification lessons.
- `references/static-site-animations.md` — Read when adding Motion animations to static HTML through vanilla JavaScript and ESM imports.
