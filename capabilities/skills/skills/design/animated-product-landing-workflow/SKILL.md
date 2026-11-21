---
name: animated-product-landing-workflow
description: Use when building or adapting an e-commerce landing page that combines GSAP animation with product-faithful AI imagery, including image replacement on an existing animated page.
type: workflow
requires: [gsap-frontend, landing-page-product-images]
---

# Animated Product Landing Workflow

## Scope
Orchestrate animation work followed by product-image work. Delegate implementation details to the sub-skills rather than reproducing their instructions. Apply this chain when both animated frontend work and faithful product imagery are required; do not force both skills onto unrelated animation-only or image-only requests.

## 1. Establish the frontend and animation contract

**load gsap-frontend with skill_read** before building or modifying the frontend.

Inputs: user brief, existing project or reference page, target framework, requested animation behavior, product source, and delivery scope.

Use the loaded skill to establish or adapt the page structure and animation implementation. Where final imagery is unavailable, reserve stable image slots rather than inventing final product visuals. For an existing page, preserve working animation and layout unless changes are requested.

Hand off to the next step:
- Project location, entry points, and preview instructions.
- Page sections and animation targets, including layout-sensitive or pinned regions.
- An asset-slot manifest covering HTML images, responsive sources, and CSS backgrounds: placement, visual role, dimensions/aspect ratio, transparency needs, filenames, and mobile/desktop behavior.
- Product-reference locations, known variants, design constraints, and explicitly excluded changes.

### Gate before image work
Confirm that the frontend can render, animation targets are identifiable, and image slots have sufficient specifications. Separate product-bearing visuals from backgrounds, problem illustrations, and utility assets. Resolve missing product references or ambiguous replacement scope before generation. Do not treat placeholder imagery as approved product photography.

## 2. Produce and integrate product-faithful assets

**load landing-page-product-images with skill_read** after the frontend contract is established.

Inputs: the frontend handoff, authoritative product references, and the user's requested output scope.

Use the loaded skill and its applicable references to create or replace imagery, validate product fidelity, and integrate approved assets into the established slots. For existing-site replacement or site-copy requests, follow the corresponding reference workflow. Preserve animation hooks and agreed layout contracts; raise any necessary structural change rather than silently redesigning the page.

Hand off for final verification:
- Integrated project or replacement-asset package, as requested.
- Final asset manifest mapping each placement to its file, dimensions, format, and product variant.
- Visual QA results, rejected or unresolved assets, and any layout changes affecting animation measurements.
- Preview or delivery locations and remaining blockers.

### Gate before acceptance
Verify that each requested slot is covered, product-bearing images match the authoritative references, and asset roles match surrounding content. Confirm responsive sources and CSS backgrounds reference the intended files. Check that replacements preserve required dimensions, transparency, and existing assets outside the agreed scope. Reject or regenerate failed assets before claiming completion.

## 3. Cross-skill acceptance

Review the integrated result at desktop and mobile sizes after images have loaded. Check that final imagery has not broken animation timing, scroll measurements, pinning, cropping, text readability, or calls to action. Verify reduced-motion behavior and that content remains usable when animation is unavailable.

If assets changed layout-sensitive measurements, return to Step 1 and reload its sub-skill for a targeted animation correction; retain approved assets. If product fidelity or placement fails, return to Step 2 and reload its sub-skill for a targeted asset correction; preserve the frontend contract. Repeat only the affected checks.

Deliver only the requested artifacts: preview or deployment when authorized, source/site package or image package as applicable, asset mapping, and a concise verification summary. Clearly identify incomplete work or unverified delivery locations; do not report success while either acceptance gate remains blocked.
