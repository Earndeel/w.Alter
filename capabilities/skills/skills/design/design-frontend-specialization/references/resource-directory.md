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
