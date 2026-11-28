# MiniMax H3 — Vast economics and LoRA evidence

Snapshot date: 2026-08-11. Prices are a dated evidence snapshot; re-query both catalogs before provisioning or quoting.

## Capability finding — updated 2026-08-11

Kie.ai and OpenRouter expose H3 reference conditioning, not arbitrary user LoRA injection. **fal.ai now exposes native MiniMax H3 LoRA inference and four H3 LoRA trainers**, so self-hosting is no longer the default capability path for custom H3 adapters.

- fal H3 LoRA inference: `minimax/h3/text-to-video/lora`, `minimax/h3/image-to-video/lora`, and `minimax/h3/reference-to-video/lora`.
- fal H3 LoRA inputs accept a URL or Hugging Face repo ID, optional `weight_name`, and `scale` from 0 to 4; the endpoint schema supports 768P, 2K, and 4K.
- fal H3 trainers: `minimax/h3/t2v/trainer`, `minimax/h3/i2v/trainer`, `minimax/h3/flf2v/trainer`, and `minimax/h3/ref2va/trainer`.
- fal H3 generation pricing observed: $0.10/s at 768p, $0.1625/s at 2K, and $0.20/s at 4K on the LoRA endpoints.
- fal H3 training pricing observed: $0.005/step (T2V), $0.01/step (I2V), $0.01/step (FLF2V), and $0.015/step (Ref2VA).
- Kie H3 text-to-video schema: `prompt`, `duration`, `resolution`, `aspect_ratio`.
- Kie H3 reference-to-video schema: `reference_image_urls`, `reference_video_urls`, `reference_audio_urls`, `prompt`, `duration`, `resolution`, `aspect_ratio`.
- OpenRouter H3 video entry: `minimax/hailuo-3`; it exposes reference inputs and `aigc_watermark` passthrough, not a LoRA/adapter field.

Official provider evidence:

- https://fal.ai/models/minimax/h3/text-to-video/lora
- https://fal.ai/models/minimax/h3/image-to-video/lora
- https://fal.ai/models/minimax/h3/reference-to-video/lora
- https://fal.ai/learn/devs/how-to-train-a-lora-for-minimax-h3
- https://docs.kie.ai/market/minimax-h3/text-to-video
- https://docs.kie.ai/market/minimax-h3/reference-to-video
- https://openrouter.ai/api/v1/videos/models

## Official H3 local model

Repository: https://huggingface.co/MiniMaxAI/MiniMax-H3

Relevant facts from the model card:

- H3-Omni-Transformer is a 33B dense transformer; the H3 encoder uses the full Qwen3-VL-32B weights.
- Native H3-Base generation targets 768p; the official 2K workflow uses H3-Regenerate-2K as a second stage.
- The official SGLang serving examples use `--num-gpus 4` and Ulysses degree 4 for FL2VA and Ref2VA.
- The full Hugging Face repository snapshot was about 498.47 GB; the FL2VA and Ref2VA task-family trees were each about 144.05 GB in the observed API metadata. Reserve additional disk for the environment, cache, outputs, and temporary files.
- The model is distributed under the MiniMax H3 community license. Check commercial/Scena use before production.

## LightX2V local LoRA path

LightX2V H3 support: https://github.com/ModelTC/LightX2V

The repository provides H3 T2AV/I2AV/L2AV/FL2AV/Ref2AV support, model/block offload, tensor/sequence parallelism, quantized inference, and a LoRA deployment guide:

- https://lightx2v-en.readthedocs.io/en/latest/deploy_guides/lora_deploy.html
- https://lightx2v-en.readthedocs.io/en/latest/deploy_guides/for_low_resource.html

The H3 DMD-LoRA 4-step configuration demonstrates actual adapter fields:

- `lora_dynamic_apply: false`
- `lora_configs: [{path, strength, alpha}]`
- block-level CPU offload and text-encoder/VAE offload
- 5 configured inference steps in the current example

Script: https://github.com/ModelTC/LightX2V/blob/main/scripts/minimax_h3/run_minimax_h3_t2av_dmd_lora_4step.sh
Config: https://github.com/ModelTC/LightX2V/blob/main/configs/minimax_h3/minimax_h3_t2av_dmd_lora_4step.json

The script uses one visible GPU, but that is a configuration pattern, not a universal VRAM guarantee. The DMD adapter is an acceleration/distillation LoRA; it must not be presented as equivalent to a character/style LoRA.

A published H3 adapter proves the format exists outside hosted Kie/OpenRouter APIs:

- https://huggingface.co/fal/MiniMax-H3-Realism-People-LoRA

That adapter is a style/realism adapter for T2V/I2V/R2V, not evidence that Kie or OpenRouter will accept arbitrary `.safetensors` files.

## Dated price evidence

### Hosted API baseline

For H3, the observed Kie catalog rates were:

| Output | Rate | Five-second equivalent |
|---|---:|---:|
| 768p | $0.08/s | $0.40 |
| 2K | $0.13/s | $0.65 |

OpenRouter's H3 video catalog also exposed $0.13/s for duration and a separate reference-image SKU. Preserve input/reference charges separately when comparing an all-in request.

### Vast live offer snapshot

The `vastai search offers` command returned verified rentable offers in this range:

| Capacity | Observed `dph_total` |
|---|---:|
| 1× RTX 4090 | approximately $0.309–$0.605/h |
| 1× RTX A6000 | approximately $0.402/h |
| 4× RTX 4090 | approximately $1.340–$1.603/h |

The cheapest offer is not automatically the correct offer. Retain GPU count, reported VRAM, disk capacity, reliability, verification, and network data; re-query immediately before a job because Vast inventory and prices move.

## Break-even table

Use:

```text
break_even_minutes = 60 × API_clip_cost / GPU_hourly_cost
local_compute_cost = GPU_hourly_cost × generation_minutes / 60
```

For a five-second H3 clip:

| Baseline | 1× GPU | 4× RTX 4090 |
|---|---:|---:|
| 768p API: $0.40 | 40–78 min on 1× 4090; about 60 min on 1× A6000 | 15–18 min |
| 2K API: $0.65 | 65–126 min on 1× 4090; about 97 min on 1× A6000 | 24–29 min |

At ten minutes of paid GPU time, four RTX 4090s cost approximately $0.22–$0.27 of compute. This is not a final per-clip cost until warm-up, retries, storage, idle time, and engineering overhead are included.

## Decision guidance — updated

- Occasional jobs or low monthly volume without LoRA: stay on a hosted API. fal H3 standard is the closest like-for-like route at $0.13/s for 2K; Kie/OpenRouter remain alternatives where their reliability or routing is better.
- A custom H3 style/character LoRA: start with fal's matching H3 trainer and LoRA inference endpoint; this avoids the 500-GB deployment and removes the capability reason to rent Vast.
- Self-hosting remains justified for private weights/data, unsupported adapter code, maximum control, high measured batch utilization, or when Fal's endpoint contract is insufficient.
- A hard LoRA/private-weight requirement is no longer automatically a self-hosting requirement: verify fal's exact H3 endpoint and adapter compatibility first.
- Do not use LightX2V/ComfyUI Turbo LoRAs as evidence of compatibility with fal custom style LoRA endpoints. Turbo/DMD LoRAs are acceleration adapters, not character/style adapters.
- Recommended pilot: train one small compatible H3 adapter on fal, run same-seed A/B tests at 768P and 2K, archive the returned `.safetensors`, then compare against the reference-only baseline before moving to Vast.
- Do not claim local 2K parity from a 768p or five-step DMD-LoRA result; test the exact Scena target tier.
