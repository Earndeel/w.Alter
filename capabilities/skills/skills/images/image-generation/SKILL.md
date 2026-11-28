---
name: image-generation
description: "Use first for any image generation or editing request (poster, product photo, logo, retouch, local Stable Diffusion/ComfyUI): which model to use and which procedure to open."
---

# Image generation — entry

## 1. Choose the model with Walter Router, never from memory

Monsieur's rule: for images, always the **best available** model, not the best value. The current choice per task
(poster, retouch, logo, image) is in `walter-router library` (or `walter-router pick <task>` / MCP `walter_route`);
2026-11-01 it was GPT Image 2.5 for every image task. Never hardcode a model in a script.

## 2. Open the procedure for the provider

| Need | Skill |
|---|---|
| Generate or edit through Kie.ai (Market API, local reference upload, batch polling, named models such as Qwen) | `kie-image-generation-operations` |
| GPT Image 2.5 through Kie specifically | `kie-gpt-image-25` |
| Fal.ai (NanoBanana, Flux; text-to-image and edit) | `fal-image-generation` |
| Fal through MCP / mcporter, exact model parameter schemas | `fal-mcp-integration` |
| Same request across providers (size/quality/aspect mapping) and the fallback chain when a provider fails | `multi-provider-image-gen` |
| Faithful product photos for a landing page (image-to-image) | `landing-page-product-images` |
| Check which OpenAI / Codex image models really exist today | `openai-codex-image-model-verification` |
| Local generation: Diffusers / ComfyUI (and ComfyUI headless with a Fal backend) | `stable-diffusion`, `comfyui`, `comfyui-headless-deployment` |
| Scena's image routing | `scena-image-routing` (domain scena) |

In reserve (open with `skill_read`, it comes back automatically): `face-grid-overlay`.

## 3. Always

- Keys come from the vault through the provider procedure; never paste one in a prompt or a file.
- Download results immediately (provider URLs expire), look at the image before reporting, and give Monsieur the
  final file path.
- Animating an image or making a video: entry `video-generation`.
