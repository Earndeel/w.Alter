---
name: video-generation
description: "Use first for any video request (generate, animate an image, UGC, ad from a reference, analyse a video): which model to use and which procedure or workflow to open."
---

# Video — entry

## 1. Choose the model with Walter Router

`walter-router library` (or `walter-router pick <task>` / MCP `walter_route`) gives the current model per video task:
animate an image (balanced, budget, action, UGC, premium), video from text, etc. Never pick from memory and never
hardcode a model. Paid benches are capped at 2 €/24 h; above that, Monsieur approves.

## 2. Open the procedure

| Need | Skill |
|---|---|
| Ad video adapted from a reference (fidelity review → production → analysis) | workflow `reference-led-ad-video-workflow` |
| The ad pipeline itself (viral reference → shot-by-shot analysis → generation → assembly) | `ad-video-pipeline` |
| Check that an adaptation stays faithful to its reference | `reference-video-fidelity` |
| Analyse a video with a model (OpenRouter video input, R2 upload for large files) | `video-analysis-pipeline` |
| Any Kie.ai video task: live contract, paid submission, polling, download, cost, QA; full model/payload reference | `kie-video-generation-operations` |
| MiniMax H3 native UGC through Kie | `minimax-h3-native-ugc` |
| Character videos that keep identity, face and teeth | `character-video-generation` |
| Selfie / POV videos: physical plausibility check | `flow-selfie-physical-qa` |
| A model-agnostic generation pipeline (I2V chaining, extensions) | `multi-model-video-pipeline` |
| R2 storage for video files | `r2-setup-and-video-pipeline` |
| Scena (multi-tenant video agent) | `scena-video-factory` (domain scena) |

In reserve (open with `skill_read`, it comes back automatically): `video-postproduction` (assembly, audio joins,
watermark removal), `higgsfield-video-generation`, `hyperframes-video-rendering` (HTML → MP4),
`reference-to-video-ugc`, `hermes-native-media-generation`, `seedance-video-prompts`.

## 3. Always

- Ad caption rules: no punctuation, captions in the lower third away from the face, one clearly named final file in
  the Mac's Downloads.
- Download provider outputs immediately, watch the result before reporting, record what was spent.

## Verify local masked editing of a source video

1. Classify the requested edit before comparing models: **spatial, prompt-guided replacement** takes a source video and a spatial mask; **removal/inpainting** fills a masked region to reconstruct the background; **temporal retake** regenerates a time interval. Do not treat a start/end time, image conditioning, or generic video-to-video support as proof of spatial masking. Check whether the documented interface accepts a mask sequence for a moving region rather than assuming a single image mask will track it.
2. Fetch the official README and, when the wording is ambiguous, the actual pipeline or CLI source with `walter_browse(url=..., content_only=True)`. For this tool's JSON-string response, read `records = json.loads(response).get('records', [])` and then `records[0].get('content', '') if records else ''`; do not look for top-level `content`. If a GitHub repo page does not expose the needed text, fetch the raw file. Start with `https://raw.githubusercontent.com/ali-vilab/VACE/main/README.md` for prompt-guided spatial editing, `https://raw.githubusercontent.com/sczhou/ProPainter/main/README.md` for removal, and `https://raw.githubusercontent.com/Lightricks/LTX-2/main/packages/ltx-pipelines/src/ltx_pipelines/retake.py` to check the scope of Retake against its actual arguments.
3. For each candidate, verify the source-video and mask inputs, what drives the fill (prompt, reference, or surrounding frames), checkpoint availability and weight license, and the documented GPU, resolution, and frame-count examples. Keep example settings separate from hard limits: VACE's 1.3B single-GPU starting point and 14B multi-GPU 720p example are not proof of minimum VRAM or maximum clip length. Treat search results for newer models as leads until official docs or code and a weight release confirm the relevant workflow.
4. When asked for a bounded documentation-only comparison, recommend separately for replacement, removal, and interval retakes. Cite the exact primary URLs within the requested budget (3–5 in this session). If OpenRouter and visual analysis are excluded, use neither and make no visual-quality claims.
