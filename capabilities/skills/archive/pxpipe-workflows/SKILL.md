---
name: pxpipe-workflows
description: Use when choosing pxpipe for context or video planning.
tags: [pxpipe, context, vision, planning, video, cost]
metadata:
  hermes:
    tags: [pxpipe, context, vision, planning, video, cost]
---

# pxpipe Workflows

Use this umbrella when deciding whether to use pxpipe for dense context transport or a Fable-planned Kie video pipeline. pxpipe is a transport/cost technique, not a replacement for the surrounding provider and artifact gates.

## Selection rules

Use the real teamchong pxpipe implementation when available and distinguish it from the older custom OpenRouter proxy. Vision compression can be valuable for a large single-turn context or planning request; normal text plus cache is usually better for multi-turn work, small tasks, or non-vision models. Do not describe the saving as Anthropic cache savings: it comes from image-token density and rendering overhead must be included.

## Video planning path

1. Materialize a brief and source the configured environment without printing keys.
2. Run the verified pxpipe planner path with the intended upstream/model and request structured `keyframe_prompt` and `motion_prompt` JSON.
3. Generate and inspect a keyframe, upload it through the provider's supported file route, submit one Kie image-to-video task, poll the saved task ID, download the result, and perform media QA.
4. Keep planning, image, and video costs separate and label observed prices as estimates or dated evidence.

## Capacity and cost discipline

Record the active pxpipe dimensions, token density, model context, rendering cost, and task length before comparing routes. A larger image is not automatically cheaper, and a benchmark from a different runtime or context size is not a universal guarantee.

## Verification

Verify the upstream endpoint, model, environment binding, structured planner output, provider task ID, downloaded artifact, and measured media properties. Never claim a cost reduction from a proxy that has not been measured under the current workload.

Exact operational commands and the real-versus-custom pxpipe comparison are routed in `references/curator-pxpipe-archive-routes.md`.
