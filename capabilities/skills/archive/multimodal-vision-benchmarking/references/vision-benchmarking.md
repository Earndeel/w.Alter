# Vision benchmark evidence snapshot

**Captured:** 2026-08-05. Treat numeric values as a dated snapshot; re-fetch before presenting them as current.

## Roboflow Vision Evals

Sources:

- https://playground.roboflow.com/models/google/gemini-3-1-flash-lite
- https://playground.roboflow.com/models/openai/gpt-5-6-luna
- https://playground.roboflow.com/vision-evals

### Gemini 3.1 Flash-Lite

The Gemini model page explicitly says it has **not yet been evaluated on the current Vision Evals**. Its displayed results are from the legacy benchmark: 67 tasks, 77 models, 68.66% pass rate, 1.86s average response per task, and $0.0003 per task. Legacy category values shown on the page include Spatial Understanding 84.2%, Document Understanding 77.8%, Defect Detection 73.3%, Object Understanding 64.3%, and Object Counting 30%. Its legacy OCR panel shows 89.96% across 229 tasks and 1.32s average response.

The same page reports the launch multimodal result of 76.8% on MMMU-Pro. MMMU-Pro is multimodal reasoning evidence, not GUI coordinate-grounding evidence.

### GPT-5.6 Luna

The current Vision Evals page is updated August 3, 2026 and covers 24 models and six tasks. Luna is shown at 71.5%, rank #12/24, $0.0005 average cost per sample, and 6.55s average speed per sample. Its current task breakdown is: Object Detection 59.9% (10.29s), Counting 66.2% (4.18s), Identification 78.1% (3.43s), OCR 88.4% (5.06s), Data Extraction 81.4% (2.94s), Reasoning low 55.0% (4.85s), and Reasoning high 60.9% (8.49s).

### Comparability decision

Do **not** report Luna's 71.5% versus Gemini's 68.66% as a clean head-to-head. They come from different Vision Evals generations, task sets, and model cohorts. The values are useful as directional context only. There was no matching public ScreenSpot/ScreenSpot-Pro/OSWorld result found for these exact two model variants in this review.

## Artificial Analysis context (not vision-specific)

AA current model records used the exact slugs `gemini-3-1-flash-lite-preview` and `gpt-5-6-luna`.

- Gemini 3.1 Flash-Lite: Intelligence Index 25, median output 338.091 tokens/s, median TTFT 4.848s, $0.25 input / $1.50 output per 1M tokens.
- GPT-5.6 Luna (max): Intelligence Index 51.2, median output 178.356 tokens/s, median TTFT 66.327s, $0.20 input / $1.20 output per 1M tokens.

These figures are general model/provider metrics, not screen-vision scores. Keep them out of the primary answer when the user asks about vision only.

## Hermes live canary observed in the review

A known synthetic dashboard image and the same deterministic marker prompt were sent through the configured Hermes runtime, not the standalone provider CLI. Three runs per model were executed with explicit provider/model/image settings and semantic output verification.

- Gemini direct via `gemini`: 11.681s median, 10.865–12.174s range, 3/3 correct.
- Luna direct via `openai-codex`: 12.329s median, 12.174–12.602s range, 3/3 correct.

These are end-to-end Hermes wall times: process startup, auth, image handling, transport, and model response. They are not pure model inference and the synthetic image does not establish robust GUI grounding. Use the protocol in the parent SKILL.md for future canaries.
