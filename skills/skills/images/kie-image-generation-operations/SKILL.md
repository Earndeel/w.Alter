---
name: kie-image-generation-operations
description: "Generate and edit images through Kie.ai Market API with local-reference upload, model-specific payloads, independent batch polling, moderation-aware retries, and verified media delivery. Also covers: kie qwen image ops."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [kie, image-generation, image-to-image, batch, moderation, ugc]
---

# Kie.ai Image Generation Operations

## When to use

Use this skill for Kie.ai image generation or editing, especially when the request includes local reference images, multiple parallel variants, character consistency, or model switching between Seedream and Nano Banana.

## Operating contract

1. Verify the exact Kie model slug and live parameter contract from the Kie model page or model-path catalog; never infer one model's fields from another.
2. Retrieve credentials from the vault (`kie/api_key`) without printing them.
3. Upload local references once through Kie file upload and reuse the resulting public URLs.
4. Build one prompt per intended composition while keeping identity constraints common across the batch.
5. Submit tasks through the Market API and preserve every returned task ID.
6. Poll every task independently until a terminal state.
7. Download each successful output immediately, verify non-zero file size, and deliver actual files with `MEDIA:` paths.
8. If only part of a batch fails, retry only failed concepts. Never repay successful generations merely because the collector exited early.

## Core endpoints

- Upload: `POST https://kieai.redpandaai.co/api/file-stream-upload`
- Submit: `POST https://api.kie.ai/api/v1/jobs/createTask`
- Poll: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...`

## Prompt architecture for referenced UGC portraits

Keep a stable identity prefix across variants:

- Explicitly state that all supplied sheets depict the same clearly adult subject.
- Name durable traits visible in the character sheet: face, hair, eyes, beard, complexion, earrings, body proportions.
- Tell the model to draw expression from the emotion sheet.
- Then vary only composition: camera position, pose, clothing, location, expression, and light.
- For authentic UGC, request front-camera or mirror perspective, imperfect crop, realistic pores/body hair, mild phone grain, and practical lighting.
- State coverage and non-explicit boundaries plainly when the brief is sensual.

## Moderation-aware behavior

- Never design semantic evasions or attempt to bypass upstream safety filters.
- A configurable model parameter may be used only when it is part of the provider's documented contract.
- Google-backed Nano Banana moderation is upstream and not exposed as a switch by Kie. If a request is rejected, adapt it to compliant lifestyle/editorial imagery or choose a provider whose published policy fits the task.
- Avoid including prohibited terms merely inside negative instructions: classifiers may trigger on the terms themselves.
- Report `creditsConsumed` on failed tasks when available; moderation failures often consume zero credits.

## Batch collector pitfall

A collector must not `raise` on the first failed task. Store per-task terminal results (`success` or `fail`), continue polling the rest, download all successes, then retry only failed concepts. One rejected frame should not hide four completed outputs.

This is an implementation requirement, not merely a recovery suggestion:

- Submit the full batch and print or persist every task ID immediately.
- Poll into a terminal-results dictionary keyed by requested output index.
- On failure, record `failMsg` and `creditsConsumed`; never abort the polling loop.
- Download successes as soon as each URL appears, preserving requested numbering.
- After all tasks terminate, retry only failed indexes with compliant prompt adjustments.
- If the foreground command is interrupted, resume collection from persisted task IDs instead of resubmitting.

## Comparative model runs

When Monsieur asks to compare image models, keep reference URLs and composition prompts fixed across providers; change only model-specific payload fields. Report the exact slug/settings, successful outputs per submission, zero-credit failures, actual `creditsConsumed`, and the USD equivalent using Kie’s live credit conversion rate.

Judge quality from a labelled contact sheet across identity fidelity, photorealism, anatomy, texture, prompt adherence, and operational reliability—not from provider marketing. See `references/ugc-model-benchmark-2026-07.md` for a worked comparison.

## Controlled expression and identity tests

An output displaying the requested generic emotion does **not** prove faithful use of an emotion sheet. Test expression fidelity separately from broad facial identity:

1. Keep crop, camera angle, clothing, background, and lighting fixed; vary only the requested expression.
2. Name the exact sheet cell or spatial location in the prompt (for example, `top-right cell`) and describe its visible action units: eyebrows, eyelids, cheeks, lips, and jaw.
3. For an open smile, treat dental identity as a first-class biometric subfeature: compare visible tooth count, individual widths and shapes, alignment/spacing, gum line, natural color, smile width, and lip geometry.
4. Build a labelled contact sheet containing the original expression crop beside every model output. Compare at matching scale before judging.
5. Distinguish three verdicts: **emotion matched**, **facial identity matched**, and **subfeature identity matched**. Never report `5/5` merely because the five generic emotions are recognizable.
6. If teeth, eyes, scars, or other small identity markers are invented or beautified, call that a partial identity failure even when the overall face is convincing.

For cross-model smile testing, send the same two references and the same prompt to every model, changing only the provider-specific payload fields. The July 2026 evidence and dental-fidelity ranking are recorded in `references/ugc-model-benchmark-2026-07.md`.

## Continuity chaining with a selected output

When Monsieur selects one generated frame as the canonical look for a continuation batch:

1. Keep the original character sheet and emotion sheet, then append the selected output as a third reference rather than replacing either sheet.
2. State an explicit reference hierarchy in the shared prompt: character sheet = durable identity, emotion sheet = expression vocabulary, selected output = primary continuity reference for current face rendering, body, wardrobe, location, light, camera treatment, and mood.
3. Describe each continuation as the next photograph from the same smartphone session. Hold wardrobe, room, light direction, camera rendering, and texture fixed; vary only body pose and requested emotion.
4. Keep expressions closed-mouth unless a visible smile is required. A good whole-face match does not guarantee dental identity.
5. Compare each output against both the character sheet and selected continuity frame before acceptance. Check jaw, nose, eye shape, facial width, hair state, and beard geometry separately; broad resemblance is insufficient.

## Parallel batch timing and interruption handling

- Submit every independent task first, persist all task IDs, then enter the polling loop. Confirm parallelism from provider `createTime` values, not from synchronous collector output.
- Measure latency from provider `costTime`, or `completeTime - createTime` when absent. Report mean, median, range, and sample count; exclude waiting tasks from completed latency statistics.
- A local collector interruption does not cancel provider-side jobs. Query persisted task IDs before resubmitting, download completed outputs, and retry only terminal zero-credit failures.
- Preserve requested numbering when retrying a partial continuation batch so replacement frames cannot overwrite or reorder successful outputs.

## Exact aspect-ratio requirements

Treat the requested ratio as an output invariant, not a prompt aspiration:

- Verify every downloaded artifact from actual pixel dimensions. For 9:16, require `width / height == 9 / 16` within rounding tolerance.
- If the live model contract exposes a ratio field, set it in addition to stating the composition in the prompt.
- If image-to-image exposes no ratio field, use a canonical reference already in the desired ratio, request the exact portrait ratio and dimensions in the prompt, then verify the returned pixels.
- `aspect_ratio: auto` may follow a landscape reference or return 4:3 even when the prompt says vertical. Never claim the ratio succeeded from payload or prompt text alone.
- Regenerate a non-conforming output when framing matters. Do not silently crop it: cropping can remove the requested pose and requires Monsieur’s approval.
- A batch is incomplete until every requested file passes the dimension check and is downloaded at non-zero size.

## Verification checklist

- Exact model slug confirmed.
- Correct model-specific reference field used.
- Reference URLs are reachable.
- Every task ID recorded.
- Every task reached a terminal state.
- Successful URLs downloaded before expiry.
- Files exist and have non-zero byte size.
- Actual pixel dimensions satisfy any requested aspect ratio.
- Delivered paths correspond to the requested count.

## Integration migrations

When replacing another provider inside a stateful Worker or agent backend, migrate both **runtime defaults and persisted routing data**. Add focused URL/model assertions before implementation, preserve the old provider only as an explicit fallback, normalize legacy model IDs, and verify a real Worker dry-run after targeted tests. For Monsieur's Scena environment, stop after local verification until he explicitly approves remote D1 migrations, Worker/Pages deployments, R2 changes, or other Cloudflare writes. For Kie reasoning endpoints, media async contracts, D1 route precedence, and legacy mock adaptation, see `references/provider-migration-stateful-workers.md`.

## Reference

See `references/model-contracts-and-batch-recovery.md` for verified payloads, upload details, response parsing, and partial-batch recovery patterns.
See `references/provider-migration-stateful-workers.md` for provider migrations in stateful Worker backends and regression-test strategy.

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **kie-image-generation-operations** — Generating with a specific named model (e.g. Qwen Image) on the Kie.ai Market API.
  Read `references/merged-kie-qwen-image-ops/kie-image-generation-operations.md`.
