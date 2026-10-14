---
name: kie-gpt-image-25
description: "Use when Monsieur requests GPT Image 2.5 via Kie."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [kie, image-generation, gpt-image-2-5, api]
---

# Kie.ai GPT Image 2.5

Use this skill for questions or implementation work involving GPT Image 2.5 through Kie.ai. Do not assume the marketing label is the API model ID, and do not silently fall back to GPT Image 2.

## When to Use

Load this skill whenever Monsieur asks about GPT Image 2.5 availability, API IDs, payloads, or Scena/Kie integration.

## Preserve user-supplied prompts verbatim

When Monsieur provides prompt wording and asks to use or retain it, pass that text exactly as written: do not translate, paraphrase, expand, add descriptors, or append negative prompts. Put technical settings such as aspect ratio and resolution in their API fields, not into the prompt. Only edit prompt text when Monsieur explicitly asks for prompt improvement or revision.

## Character-sheet fidelity

When likeness matters and the supplied reference is a multi-view character sheet, a full-sheet input can dilute facial identity—especially at 1K. Without changing a user-specified exact prompt, prepare a clean close-up face crop from the same sheet and include it alongside the full sheet in `input_urls` when the endpoint supports multiple references. Inspect the generated face against the reference before claiming identity fidelity; report drift plainly.

## Reference roles and moderation diagnosis

- Verify reference contents visually before assigning face/product roles; upload numbering does not establish their order in `input_urls`.
- When an adult sensual-fashion brief uses an age-ambiguous face, confirm adulthood before generating the sensual treatment.
- After repeated moderation failures, do not repay another whole batch. When live testing is authorized, bound diagnosis to genuinely neutral controls: text-only still life, fully clothed portrait from the face reference, and product-only image from the garment reference. Keep original inputs unchanged; never disguise them to evade filtering.
- Separate successful endpoint/reference controls from the requested composition: independent reference acceptance does not prove that the combined worn-garment scene will pass.
- Label a clothed presentation with a separately displayed product as a changed composition, not success at making the subject wear it.
- Check garment construction against a magnified original before adding verbal constraints; do not invent hardware or fabric panels from a blurry detail. Compare face geometry and garment geometry separately, and disclose remaining drift.
- When reusing a collector, inspect actual function signatures and manifest keys first. Derive expected counts from the submitted jobs, and validate pixels against each job's requested resolution rather than assuming every diagnostic is a five-image 2K batch.

## Verify live availability first

Query Kie's public model-path catalog at `https://api.kie.ai/api/v1/playground/model-paths` and filter for `gpt-image`. The catalog is the authority for callable path IDs; the product page is `https://kie.ai/gpt-image-2-5`.

The live catalog verified on 2026-09-26 returned these GPT Image 2.5 paths:

- `gpt-image-2-5-flare-text-to-image`
- `gpt-image-2-5-flare-image-to-image`
- `gpt-image-2-5-sunburst-text-to-image`
- `gpt-image-2-5-sunburst-image-to-image`

The generic ID `gpt-image-2.5` is not a Kie model path. Flare is the lower-latency/general-use option; Sunburst is positioned for more premium, controlled outputs. Recheck the catalog before each new integration because Kie changes model paths.

## Product-page input contract

Kie's live GPT Image 2.5 page lists these fields:

- Text-to-image: required `prompt`; optional `aspect_ratio`, `resolution`, `background`.
- Image-to-image: required `prompt` and `input_urls` (array); optional `aspect_ratio`, `resolution`, `background`.
- `aspect_ratio`: `auto`, `1:1`, `3:2`, `2:3`, `16:9`, `9:16`, `4:3`, `3:4`, `21:9`, `27:16`, `16:27`, `9:8`, `8:9`.
- `resolution`: `1K`, `2K`, `4K`.
- `background`: `transparent`, `opaque`, `auto`.
- `27:16`, `16:27`, `9:8`, and `8:9` are 1K-only; the other listed ratios support 2K/4K.
- For 2K/4K transparent output, Kie's page says the prompt must describe an isolated subject with no backdrop/scenery/shadow; I2I prompts should explicitly request subject extraction and transparent background.

Kie's public GPT Image 2.5 page exposes UI fields but defers the exact request endpoint and API request format to model-specific API documentation. Do not infer end-to-end compatibility from catalog presence alone. Confirm the current model-specific docs before making a paid generation request.

## Scena adapter mismatch to check

The existing Scena Kie adapter inspected on 2026-09-26 only wired the previous GPT Image 2 paths (`gpt-image-2-text-to-image` and `gpt-image-2-image-to-image`). Its schema builder emitted `prompt`, optional `input_urls`, and forced `aspect_ratio` to `auto`; it did not pass `resolution` or `background`. Scena's orchestration catalog/defaults also exposed only those v2 routes.

When asked why GPT Image 2.5 failed through Scena, identify this as an adapter/model-ID/schema gap, not proof that Kie lacks GPT Image 2.5. For implementation, add all four exact paths and validate each mode's payload independently; update provider schemas, model catalog/defaults, and tests. Never map 2.5 silently to the 2.0 adapter.

## Cost and verification guardrail

A model-path catalog read is non-generative and does not verify credits, auth, or successful rendering. Do not submit a generation task or spend Kie credits just to diagnose availability unless Monsieur explicitly asks for a live generation test. If the user failed directly in Kie's Playground rather than through Scena, get the exact error text before attributing it to auth, quota, or a backend fault.