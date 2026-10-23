# MiniMax H3 LoRA provider compatibility

Last live verification: 2026-08-11.

## Verdict

MiniMax H3 is **not documented as accepting user-supplied LoRA/adapters** through either Kie.ai or OpenRouter. Treat it as `not_exposed / unverified`, not as supported. The fact that OpenRouter describes H3 as “open-weights” does not imply that its hosted API loads arbitrary adapters.

A reference input is not a LoRA:

- reference conditioning supplies images/video/audio at inference time;
- LoRA inference loads a trained adapter, normally with an adapter identifier/path and a weight/scale;
- fine-tuning/training an adapter is separate from consuming it during generation.

## Kie.ai evidence

Official model pages:

- https://docs.kie.ai/market/minimax-h3/text-to-video
- https://docs.kie.ai/market/minimax-h3/image-to-video
- https://docs.kie.ai/market/minimax-h3/reference-to-video

The live schemas expose:

- text-to-video: `prompt`, `duration`, `resolution`, `aspect_ratio`;
- image-to-video: `first_frame_url` and/or `last_frame_url`, plus the normal generation fields;
- reference-to-video: `reference_image_urls`, `reference_video_urls`, `reference_audio_urls`, `prompt`, `duration`, `resolution`, `aspect_ratio`.

The H3 schemas contain no documented `lora`, `adapter`, `adapter_url`, `lora_url`, adapter weight/scale, or fine-tuning field. Do not send a guessed field or silently use another Hailuo model.

## OpenRouter evidence

Live video catalog: https://openrouter.ai/api/v1/videos/models

The H3 entry is `minimax/hailuo-3` / canonical slug `minimax/hailuo-03-20260730`. It advertises 2K output, 5–15 second durations, and pricing SKUs for duration and reference images. The hosted video request accepts `input_references` for reference media; the catalog's listed passthrough parameter is `aigc_watermark`. No LoRA/adapter injection or fine-tuning field is exposed in the video contract.

## Operational decision

For Scena, use H3 with reference sheets when visual consistency is sufficient. If an actual LoRA is a hard requirement, deploy the published H3 weights on a GPU/runtime that explicitly supports PEFT/LoRA loading and separately verify adapter format, target modules, VRAM/runtime, and licensing. Do not represent a reference-image workflow as LoRA support.

## Reverification rule

Before making a new provider recommendation, re-fetch the provider's current H3 schema/catalog and search the structured request fields for explicit adapter support. A model page, pricing row, or generic provider claim is insufficient evidence; the capability must appear in the model-specific generation contract.
