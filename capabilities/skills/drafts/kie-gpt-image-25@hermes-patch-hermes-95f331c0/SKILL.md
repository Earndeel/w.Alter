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

## API contract discovery and recoverable generation

- Discover model-specific documentation links in `https://docs.kie.ai/llms.txt` before guessing a path. GPT Image 2.5 docs live under `/market/gpt/`, not `/market/gpt-image-2-5/`; the latter can be a 404 despite a large HTML response. Try Walter Browse first and use the Markdown source for contract verification when extraction fails.
- Read `https://docs.kie.ai/market/gpt/gpt-image-2-5-sunburst-image-to-image.md` and `https://docs.kie.ai/market/gpt/gpt-image-2-5-flare-image-to-image.md` for the respective OpenAPI specifications. Submit `POST https://api.kie.ai/api/v1/jobs/createTask` with `model` and `input` containing the exact `prompt`, `input_urls`, and explicitly chosen `aspect_ratio`, `resolution`, and `background`. Check the JSON `code`, not HTTP 200 alone. Never use a generic image tool that cannot select the requested variant.
- Upload local references through `https://kieai.redpandaai.co/api/file-stream-upload` using Bearer auth, multipart `file`, and `uploadPath`/`fileName`. Read back the returned URL and compare SHA-256 to the original before submitting it; preserve the unchanged full reference when also adding a same-source face crop.
- Persist each task ID, exact payload, reference hashes, and model in a manifest immediately after submission. Collect through `GET /api/v1/jobs/recordInfo?taskId=...`; read back the exact ID, model and nested `param.input`, which may itself be a JSON string. Never replay an ambiguous timed-out paid POST.
- Require terminal `state=success`, decode `resultJson.resultUrls`, download the actual image, and verify its format, dimensions, expected count and visual fidelity before delivery. Keep `creditsConsumed` from the provider; do not fabricate billing from missing fields. For Desktop delivery use `MEDIA:/absolute/path`, not a localhost server or a promise to retrieve it later.

## Scena adapter mismatch to check

The existing Scena Kie adapter inspected on 2026-09-26 only wired the previous GPT Image 2 paths (`gpt-image-2-text-to-image` and `gpt-image-2-image-to-image`). Its schema builder emitted `prompt`, optional `input_urls`, and forced `aspect_ratio` to `auto`; it did not pass `resolution` or `background`. Scena's orchestration catalog/defaults also exposed only those v2 routes.

When asked why GPT Image 2.5 failed through Scena, identify this as an adapter/model-ID/schema gap, not proof that Kie lacks GPT Image 2.5. For implementation, add all four exact paths and validate each mode's payload independently; update provider schemas, model catalog/defaults, and tests. Never map 2.5 silently to the 2.0 adapter.

## Cost and verification guardrail

A model-path catalog read is non-generative and does not verify credits, auth, or successful rendering. Do not submit a generation task or spend Kie credits just to diagnose availability unless Monsieur explicitly asks for a live generation test. If the user failed directly in Kie's Playground rather than through Scena, get the exact error text before attributing it to auth, quota, or a backend fault.