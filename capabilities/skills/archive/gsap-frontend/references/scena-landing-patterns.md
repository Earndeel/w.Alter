# Scena Landing Page — GSAP Patterns Reference

Live: https://scena.walter-ai.cloud (scena-portal project on Cloudflare Pages)
Source: /root/projects/scena-cloudflare/pages/portal/index.html

## Patterns used

| Section | Plugin | Technique |
|---|---|---|
| Hero | SplitText | `rotateX: -90°` + `perspective: 1000px` — 3D text entrance |
| Hero | ScrollTrigger | Orbs parallax at different scrub speeds (1, 1.5, 2) |
| Hero | gsap.to | Orbs floating with `repeat: -1, yoyo: true` |
| Product suite | SplitText | Words staggered with `rotateZ: 3°` + `overflow: hidden` mask |
| Cards | ScrollTrigger | `y: 60, opacity: 0, stagger: 0.12` entrance |
| Split section | ScrollTrigger | Simple fade-in on scroll |
| API section | ScrollTrigger | Text left slide, code block right slide |
| SVG draw | DrawSVGPlugin | 8 paths drawn sequentially with `stagger: 0.15` |
| Pinned panels | ScrollTrigger | 3 panels pinned at `+=130%`, timeline scrubbed with entry/exit |
| Use cases | ScrollTrigger | Cards stagger entrance |
| CTA | ScrollTrigger | Fade-in stagger |
| Global | ScrollSmoother | `smooth: 1.5` — inertial smooth scroll across entire page |
| Nav | ScrollToPlugin | Smooth scroll to anchors |

## Production notes

- **All 13 GSAP plugins served locally** from `/assets/gsap/` (not CDN) because premium plugins (SplitText, ScrollSmoother, DrawSVG, etc.) aren't on jsdelivr
- **ScrollSmoother wrapper**: `#smooth-wrapper` > `#smooth-content` pattern
- **Dashboard hidden**: When user authenticates, landing hides, dashboard shows. GSAP only initialized on landing.
- **Auth preserved**: Google Sign-In + email/password via Better Auth, all API calls to `api.walter-ai.cloud`
- **Custom cursor**: `mix-blend-mode: difference` + lerp follower
- **Effects**: Film grain (SVG noise), vignette, global progress bar, magnetic buttons

## Stack

- GSAP 3.13+ (npm `gsap@latest`)
- 13 plugins: Core, ScrollTrigger, ScrollSmoother, ScrollToPlugin, SplitText, ScrambleTextPlugin, DrawSVGPlugin, MorphSVGPlugin, MotionPathPlugin, Flip, Observer, CustomEase, EasePack
- Fonts: Space Grotesk + JetBrains Mono (Google Fonts)
- Colors: `#030303` bg, `#8b5cf6` (purple), `#06b6d4` (cyan), `#f472b6` (pink)
