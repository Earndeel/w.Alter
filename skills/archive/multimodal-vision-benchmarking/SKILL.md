---
name: multimodal-vision-benchmarking
description: Use for vision, screen, OCR, or GUI benchmark comparisons.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [multimodal, vision, screen-analysis, gui-grounding, ocr, benchmarking]
    related_skills: [model-benchmark-comparison, aa-intel-vs-cost-scraper, aa-pareto-model-optimizer]
---

# Multimodal vision benchmarking

## Trigger

Use this skill when Monsieur asks which model is better or faster for:

- screenshot or screen analysis;
- GUI/computer-use perception;
- click-target or coordinate grounding;
- OCR, document extraction, charts, or visual question answering;
- image understanding or multimodal model routing.

If the request is explicitly about **vision**, do not lead with general LLM Intelligence, coding, or generic agentic scores. Those may be reported only as clearly labeled non-vision context.

## Core rule: separate four axes

Never collapse these into one verdict:

1. **Visual accuracy** — does the model identify/read/interpret the image correctly?
2. **GUI grounding** — does it select the correct screen element or coordinates?
3. **Latency** — how long until a usable answer or action is available?
4. **Cost** — provider price or benchmark cost per sample/task.

A model can be excellent at visual question answering and still be unreliable at clicking a small GUI target. The benchmark should match the intended role.

## Evidence hierarchy

Use the most task-specific evidence available:

1. **GUI grounding / computer use:** ScreenSpot, ScreenSpot-Pro, OSWorld, or a comparable target-selection/action benchmark. These are the closest evidence for a screen-control perception layer.
2. **Vision task suites:** object detection, counting, identification, OCR, data extraction, and visual reasoning (for example, Roboflow Vision Evals).
3. **Multimodal reasoning:** MMMU-Pro, MathVista, ChartQA, document VQA, and OCR suites. These measure image understanding, not necessarily click-coordinate grounding.
4. **Live canary:** same image, same prompt, same provider/runtime, at least three runs, with semantic correctness checked.

Do not present MMMU-Pro or a generic Vision Evals score as evidence of ScreenSpot/OSWorld performance. If no GUI-grounding benchmark exists for the exact model, say so plainly.

## Comparability gate

Before calculating a difference or declaring a winner, verify:

- same benchmark family and version;
- same task set and scoring rule;
- same model variant and reasoning tier;
- same evaluation date/model cohort;
- same input modality, image size, and prompt protocol where documented;
- same provider path when comparing latency.

If one model is listed on a legacy benchmark and the other on a current release, show both figures but mark them **not directly comparable**. Never subtract their scores or compare their ranks as if they came from one table.

## Live latency protocol

For a reproducible screen canary:

1. Create or select one known screenshot-like image with several unambiguous labels and colors.
2. Use the exact same prompt for every model, requesting a short, deterministic answer containing semantic markers.
3. Invoke the configured Hermes runtime with explicit model, provider, image, and quiet flags; do not use a standalone provider CLI that may use another endpoint or auth path.
4. Run at least three identical calls.
5. Measure wall-clock time around the complete invocation and record exit status.
6. Verify the answer contains the required semantic markers; an exit code alone is not success.
7. Report median, minimum, maximum, and the number of correct runs.
8. State that end-to-end time includes process startup, auth, image upload, transport, and response generation. It is not pure model inference.

Use provider-level TTFT/output-speed metrics only as a separate table. Do not mix them with Hermes end-to-end wall time.

A synthetic canary establishes basic recognition and transport latency only. It does not establish robust grounding on real applications, canvas elements, tiny controls, menus, or dynamic interfaces.

## Routing recommendation

For a computer-use pipeline, a practical split is often:

- fast multimodal model for first-pass perception, OCR, and stable screen state;
- stronger model for ambiguous screens, action planning, recovery, and safety checks;
- accessibility/UI tree (AX/UIA) for deterministic element targeting whenever available.

Do not recommend this split solely from tokens-per-second. Check visual accuracy, grounding evidence, error recovery, and cost for the actual workflow.

## Output format

Lead with the requested axis. For a screen-vision comparison, use:

```text
Vision benchmark evidence
- Model A: score, benchmark/version, task breakdown, latency/cost
- Model B: score, benchmark/version, task breakdown, latency/cost
- Comparability: direct / partial / not comparable

Live canary
- image/prompt protocol
- median/min/max wall time
- correctness count

Verdict for screen perception
- what the evidence proves
- what it does not prove
- recommended routing
```

Avoid using a generic model leaderboard as the primary answer to a vision-only question.

## References

- `references/vision-benchmarking.md` — benchmark families, source links, and the legacy/current Vision Evals comparability case captured during the Luna/Gemini review.
