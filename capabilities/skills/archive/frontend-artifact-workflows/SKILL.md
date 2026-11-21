---
name: frontend-artifact-workflows
description: Use for frontend artifacts, visual design, and browser QA.
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [frontend, visual-design, animation, tailwind, games, qa]
---

# Frontend Artifact Workflows

Use this class-level skill for frontend prototypes, landing pages, visual systems, animated backgrounds, interactive sketches, games, and browser-based QA. Build the smallest runnable artifact, then verify behavior and rendering rather than trusting source appearance.

## Always-on rules

- Establish audience, task, visual hierarchy, responsive constraints, and acceptance criteria before styling.
- Prefer semantic structure, accessible controls, progressive enhancement, and a coherent design system over isolated effects.
- Keep dependencies and build tooling proportional to the artifact; avoid a framework or animation library when a small local implementation is clearer.
- Treat generated media, fonts, shaders, and third-party assets as explicit inputs with fallbacks and loading/error states.
- Verify the served artifact through a real browser at target viewports; a polished static shell or successful build is not functional QA.

## Design and positioning

- Position the page for a specific audience and job-to-be-done; technical buyers and consumer buyers need different proof, language, hierarchy, and calls to action.
- Use a deliberate visual system: typography roles, spacing scale, color/contrast, borders/radii, motion language, and interaction states.
- Draw inspiration from established systems without copying brand assets or assuming a reference site's implementation.
- Keep hero content, proof, feature explanation, objections, and conversion action in a readable order; make the primary action obvious on mobile and desktop.

## Visual effects and sketches

- Layer animated backgrounds from restrained gradients, particles/noise, geometry, and content-safe overlays; keep text contrast and reduced-motion behavior intact.
- In p5.js or canvas work, separate setup, state, draw/update, resize, input, and cleanup; bound particle/object counts and stop animation when the surface is hidden.
- Prefer CSS/SVG/Canvas primitives that degrade predictably; do not let a shader or canvas failure remove the semantic content.

## Tailwind and component implementation

- Confirm the Tailwind/vite version and use the active configuration model; do not mix incompatible v3/v4 directives or assume a config file is loaded.
- Keep reusable components and tokens coherent, avoid arbitrary one-off classes, and implement loading, empty, error, hover, focus, disabled, and reduced-motion states.
- Verify the generated CSS contains the intended utilities and that production build paths include the classes used by the artifact.

## Interactive games and prototypes

- Define the core loop, controls, reset/restart behavior, score/state transitions, and failure/recovery paths before polishing.
- Exercise the start flow, actual interaction, state change, and replay; a changing canvas or screenshot alone does not prove gameplay.
- Keep effects, timers, event listeners, and animation frames bounded and disposable.

## Browser QA

1. Serve the final artifact from the intended path and verify HTTP response and asset references.
2. Open it in a real browser at representative viewport sizes.
3. Exercise primary interactions, keyboard/focus paths, responsive layout, and error/loading states.
4. Inspect console/network errors and capture screenshots of important states.
5. Confirm no missing scripts, broken routes, overflow, unreadable text, clipped controls, or stale placeholder copy.
6. Report visual and behavioral results separately, including any environment-dependent limitations.

## Completion contract

Deliver the runnable artifact plus evidence that the requested interaction works in the served browser. Do not call a design-only screenshot a verified product.
