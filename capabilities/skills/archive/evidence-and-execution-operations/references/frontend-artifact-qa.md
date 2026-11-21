# Frontend artifact and browser QA depth

## Design intake

Inspect supplied brand files, screenshots, repository components, tokens, copy, assets, and constraints before styling. Choose the artifact form deliberately—self-contained HTML/SVG, clickable flow, component lab, fixed-size deck, or the repository's actual stack—and define audience, job, hierarchy, responsive behavior, accessibility, interaction states, and output format.

Keep content factual, label placeholders, and establish typography, spacing, color and contrast, surfaces, borders, radii, motion, and responsive tokens before polishing. Use a design system as vocabulary rather than copying a proprietary surface.

## Canvas, diagrams, sketches, and games

Separate setup, state, update/draw, resize, input, export, and cleanup. Use deterministic seeds, bound particles/listeners/frames, stop work when hidden, and preserve semantic content when canvas or shaders fail. Choose diagram shapes, connectors, parent/child relations, anchors, dimensions, and wrapping from the target renderer's actual schema; keep geometry deterministic and place labels outside boundaries. Define game controls, score/state transitions, reset/restart, and failure recovery before visual polish, then smoke-test representative interactions and replay.

## Frameworks and media

Confirm the active Tailwind/Vite version and configuration model; do not mix incompatible directives or assume a config is loaded. Prefer CSS/SVG/Canvas primitives that degrade predictably, keep effects disposable, and provide loading and error fallbacks for fonts and media.

## Browser verification

Serve the final artifact from its intended path and check HTTP responses and asset references. Open representative viewports in a real browser; exercise primary interactions, keyboard and focus paths, responsive layout, loading and error states, and reduced motion. Inspect console and network errors and capture important states. Reject missing scripts, broken routes, overflow, unreadable text, clipped controls, stale placeholders, or a design-only screenshot presented as functional proof.
