---
name: openai-codex-image-model-verification
description: "Use when checking OpenAI/Codex image models. Verify live."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [openai, codex, image-generation, model-catalog, verification]
---

# OpenAI/Codex image-model verification

## Workflow

1. Check the current official OpenAI developer changelog and model pages for the exact model IDs, release date or snapshot, supported APIs, and quality settings.
2. Check the live Hermes configuration to identify the active image backend and whether `image_gen` is enabled.
3. Inspect or execute the active backend's model enumerator, and check the current upstream integration source when the local checkout may be stale.
4. Report two separate facts:
   - **Officially available:** what OpenAI documents and exposes through the Image API or Responses API image-generation tool.
   - **Currently exposed here:** what the active Hermes/Codex integration actually lists and accepts.
5. Distinguish real API model IDs from virtual local quality-tier IDs. Do not claim a newly announced model is selectable in Hermes until its provider catalog accepts the exact ID.
6. Never modify configuration, update Hermes, or send a generation request merely to answer a catalog question unless Monsieur explicitly asks for that action.

## Guardrails

- Treat local model lists and release notes as snapshots; verify time-sensitive availability against live official sources.
- Do not silently substitute an older model when a requested new model is not yet wired into the active integration.
- If the local checkout is behind upstream, state that explicitly and verify upstream source before concluding that support is absent.
- Keep the orchestration model separate from the image model: a Responses/Codex host model may call a distinct image-generation model.
