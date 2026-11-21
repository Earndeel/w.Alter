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
