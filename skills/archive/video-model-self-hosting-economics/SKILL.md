---
name: video-model-self-hosting-economics
description: "Use when comparing hosted video APIs with self-hosted GPUs."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [video, self-hosting, gpu, vast, lora, cost-optimization, inference]
    related_skills: [vastai-gpu-workflow, kie-video-generation-operations, model-value-analysis]
---

# Video Model Self-Hosting Economics

Use this skill when Monsieur asks whether an open-weight video model should run on rented GPU capacity instead of a hosted API, especially when LoRA, custom adapters, private weights, batch volume, or API capability gaps are involved.

## When to Use

Load this skill for API-versus-GPU cost comparisons, Vast/RunPod/Modal capacity decisions, open-weight video deployment, LoRA or adapter serving, self-hosted batch economics, and hybrid provider routing.

## Decision rule

Do not recommend GPU rental from the hourly rate alone. First establish whether the local path is technically equivalent to the hosted path, then compare the full cost of a warm generation and the operational burden.

There are two separate questions:

1. **Capability decision:** does self-hosting unlock a required feature such as arbitrary LoRA loading, custom checkpoints, private media, or unsupported resolution/control?
2. **Economic decision:** after GPU time, storage, model download, warm-up, retries, idle time, engineering, and maintenance, is it cheaper per successful clip?

A GPU can be justified by capability even when it is not the cheapest raw generation path. Conversely, a large nominal saving is not real if the local implementation is slower, lower-resolution, or unreliable.

## Workflow

### 1. Freeze the comparison unit

Use one explicit baseline, normally one 5-second clip, and record:

- model and task family: T2V, I2V, reference-to-video, editing;
- duration, aspect ratio, resolution, frame rate, and audio mode;
- reference-image/video/audio count and input charges;
- quality path: native model, quantized model, distilled/LoRA acceleration path, or offloaded path;
- API clip price and local output quality.

Never compare a hosted 2K clip with a local 768p or low-step preview and call the result equivalent. Report the mismatch instead.

### 2. Verify local feasibility before pricing it

Read the official model card and the chosen inference framework. Record:

- parameter count and encoder size;
- checkpoint size and required disk;
- published GPU count or VRAM guidance;
- CPU/RAM offload, quantization, tensor/sequence parallelism, and cache support;
- whether the exact LoRA format and task family are supported;
- commercial license and acceptable-use terms.

Classify adapters explicitly:

- **style/identity LoRA:** changes the generated visual distribution;
- **prompt-rewriter LoRA:** changes the prompt/conditioning model, not the generator weights;
- **distillation/acceleration LoRA:** reduces inference steps and may change the quality/speed trade-off;
- **reference conditioning:** an image/video/audio input, not a LoRA.

An “open weights” label does not prove that a hosted API accepts arbitrary adapters.

### 3. Query live GPU offers

Use the provider's live offer search immediately before provisioning. Preserve `dph_total`, GPU count, GPU memory, reliability, verification status, disk capacity, and network speed. Do not hard-code a host ID or a historical hourly price in application routing.

For Vast, destroy unused instances. Stopping an instance can continue to incur storage charges. Templates or snapshots are worthwhile only when model-download and environment setup costs will be amortized by the expected workload.

### 4. Calculate break-even wall time

For one clip:

```text
break_even_minutes = 60 × API_clip_cost / GPU_hourly_cost
local_compute_cost = GPU_hourly_cost × wall_time_minutes / 60
```

Run the calculation at both the cheapest and conservative live GPU offer. Add a separate fixed-cost line for environment setup, model download, adapter training, disk retention, failed generations, and engineering time.

For monthly volume:

```text
monthly_local_cost = paid_GPU_hours + storage + setup_amortization + retries
monthly_api_cost = successful_clips × API_clip_price
```

Do not divide by nominal model steps unless an actual wall-clock benchmark has been measured.

### 5. Run a bounded pilot

Before renting a multi-GPU cluster:

1. Use one verified GPU with the smallest model family and disk that can work.
2. Run one cold-start test and at least three warm generations.
3. Measure peak VRAM, system RAM, disk, model load time, generation time, output dimensions, audio, decode success, and LoRA effect.
4. Destroy the instance after the test if no persistent service is required.
5. Escalate to multi-GPU only when the single-GPU path is memory-safe but too slow, or when the official serving path requires parallelism.

A successful model load is not a successful video pipeline: verify the actual MP4, audio stream, duration, resolution, and adapter effect.

## LoRA-specific guardrails

- Do not send a guessed `lora_url` or `adapter` field to a hosted provider whose model contract does not list it.
- Do not call reference-to-video “LoRA support.”
- Validate the adapter's base model, target task family, rank/format, scale/strength semantics, and trigger words.
- Treat an acceleration LoRA as a different operating point from a character/style LoRA.
- Include training cost separately; inference economics do not pay for dataset preparation or adapter training automatically.

## Recommendation format

Lead with one verdict:

- **Hosted API:** best for low/intermittent volume, turnkey production, or when local quality is not equivalent.
- **GPU rental:** best when LoRA/private weights/API capability is mandatory and the measured volume amortizes setup/storage.
- **Hybrid:** API default plus a warm or on-demand GPU lane for LoRA jobs and batch work.

Then show the baseline API clip cost, live GPU rate, break-even wall time, measured pilot result (or clearly mark it as unmeasured), and the single next test required for a production decision.

## Reusable evidence

The MiniMax H3 case, including official checkpoint size, LightX2V LoRA configurations, live Vast offer ranges, API baselines, break-even calculations, and 2K equivalence caveats, is preserved in `references/minimax-h3-vast-economics.md`.

## Pitfalls

- A provider price is not universal: normalize model version, resolution, duration, audio, references, and billing unit first.
- A four-GPU official deployment and a one-GPU CPU-offloaded demo are not the same quality/latency tier.
- A local 768p workflow may not reproduce a hosted 2K workflow; verify the second-stage upscaling/regeneration path.
- Model downloads can be hundreds of GB; one-time download time and persistent disk are part of the cost.
- Vast offers fluctuate and may be interrupted or unreliable; include retries and do not select solely on the lowest `dph_total`.
- Never report a cost saving without a real wall-clock measurement or an explicit break-even condition.
