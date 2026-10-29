---
name: ad-video-pipeline
description: Modular video ad creation pipeline — reverse-engineering viral videos from foreplay.co → shot-by-shot analysis → Kling V3 Pro generation with multi-shot consistency via @Element → Google Drive delivery. Use when creating cosmetic/beauty video ads from reference videos.
version: 1.0.0
---

# Ad Video Pipeline — Modular Architecture

**Purpose:** Reverse-engineer viral videos from foreplay.co, analyze them shot-by-shot, adapt for cosmetic/beauty target audience, and regenerate via Kling V3 Pro.

## Always-on rules

**Purpose:** Reverse-engineer viral videos from foreplay.co, analyze them shot-by-shot, adapt for cosmetic/beauty target audience, and regenerate via Kling V3 Pro.

- Lucas approves or requests modifications
- Takes approved payload

## Audio contract — prerequisite for prompts and delegation

- Resolve the requested audio source before preparing any generation or subagent brief. A requirement for audio generated natively by the video model forbids a separate TTS voice, overdubbing, or externally synthesized music; an audio stream muxed into the final video does not establish native provenance.
- Put the exact approved dialogue and the native-audio requirement in each speaking shot's generation prompt and supported provider settings. Remove contradictory negatives such as `no audio`, `no speech` or `VO added in post`; do not assume native-audio support from the model name or an audio stream alone.
- Keep visible speakers' original synchronized image and sound paired through edits. Time captions against the actual generated dialogue, not a substitute TTS transcript; verify native source provenance, exact spoken wording, lip-sync and intelligibility before accepting a shot.
- When an audio-source correction supersedes an existing brief, invalidate conflicting prompts and downstream audio artifacts for delivery, preserve them as history, and propagate the corrected contract to all delegates. Distinguish preserved identity references from usable dialogue takes, and obtain fresh approval before paid regenerations when the existing approval forbids them.

## References (read with skill_read(name, file_path=...))

- `references/architecture.md` — Read when running pipeline stages, generating or reviewing payloads, or working with the model registry and generation APIs.
- `references/database-and-operations.md` — Read when querying or migrating SQLite, running video analysis, editing prompt templates, or maintaining the dashboard.
- `references/files.md` — Read when locating implementation files, canonical model prompts and schemas, legacy components, or output artifacts.
- `references/model-manager.md` — Read when creating, editing, or deleting model configurations through the dashboard or CRUD APIs.
- `references/technical-workflows.md` — Read when downloading references, scraping Notion, detecting shots, or troubleshooting browser access and video payloads.
