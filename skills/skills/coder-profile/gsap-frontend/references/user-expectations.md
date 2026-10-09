# User Expectations for Animation Quality

## When Lucas says "c'est décevant" / "pas mieux ?"

This signals the animation level is too basic. He expects the **full cinematic stack**, not just fade-in reveals.

**Weak (rejected):**
- Simple `gsap.to()` with `opacity: 1, y: 0`
- ScrollTrigger `toggleActions` without scrub/pin
- Cards sliding in one by one
- Vanilla CSS glassmorphism + basic JS scroll reveals

**Strong (approved):**
- **ScrollSmoother** — smooth scroll is the first filter (immediately feels premium)
- **SplitText** with `rotateX: -90°` + `stagger: 0.03` — 3D text reveals
- **Multiple pinned sections** with timeline scrubbed (4+ panels)
- **SVG Draw + Morph** at least one of each
- **ScrambleText** for one section
- **Custom cursor** (dot + trail with lerp + mix-blend-mode: difference)
- **Film grain + scanlines + vignette** CSS overlays
- **Parallax orbs/spheres** with blur and different scrub speeds
- **Magnetic buttons** (hover tilt)
- **Global scroll progress bar**
- **Data points** floating with animated values

## Minimum "Cinematic" Stack

Every landing/informational page should have at minimum:
1. ScrollSmoother
2. SplitText on the hero H1
3. At least 1 pinned section with scrubbed timeline
4. Custom cursor
5. Grain + vignette
6. Magnetic buttons

Without these, the page will feel "basic" to Lucas. The difference between "basic" and "ok" is entirely in the plugins used, not in the number of tweens.

## Deployment Checklist

Before showing Lucas:
- [ ] ScrollSmoother initialized
- [ ] Hero text has SplitText with 3D transforms
- [ ] At least one DrawSVG or MorphSVG section
- [ ] Custom cursor visible
- [ ] Grain/vignette visible
- [ ] No console errors
- [ ] Mobile responsive (cursor hidden, grid single column)
- [ ] All premium plugins served locally (not CDN — they 404)
