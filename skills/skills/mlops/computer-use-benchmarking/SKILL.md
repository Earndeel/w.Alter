---
name: computer-use-benchmarking
description: Use for real Computer Use vision-model benchmarking.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [computer-use, vision, benchmarking, latency, model-selection]
    related_skills: [computer-use, model-benchmark-comparison, model-id-lookup]
---

# Computer Use Model Benchmarking

Compare models for a desktop-agent workload without confusing three different properties:

1. **Visual capability** — did the model correctly read the screen?
2. **Perception latency** — how long did capture → upload → visual response take in the real Hermes path?
3. **Action reliability** — did the agent choose and execute the correct element/coordinate, then verify the resulting state?

A model can be fast at image captioning and still be unsafe at clicking. Generic multimodal leaderboards, token throughput, and a single successful screenshot read do not establish Computer Use superiority.

## Trigger

Load this skill when the user asks which model is faster or better for:

- screen reading or GUI perception;
- Computer Use model routing;
- screenshot-to-action latency;
- comparing a fast vision auxiliary model with a slower reasoning model;
- deciding whether a model should be primary, fallback, or escalation-only.

## Operating protocol

### 1. Freeze the comparison surface

Before running the test, record:

- exact model IDs and provider routes;
- the same screenshot fixture for every candidate;
- the same prompt and output format;
- Hermes CLI/API flags, toolsets, reasoning effort, timeout, and config source;
- whether each call is a fresh process or a persistent warm session;
- the date and benchmark source version for any external leaderboard numbers.

Never silently replace a requested model ID. Validate the ID through the provider's actual registry/configuration path; OpenRouter lookup is appropriate only when OpenRouter is the route being tested.

### 2. Benchmark the perception leg

Use the same screenshot and a prompt that requires exact image-grounded values. Include a marker or set of values visible in the fixture, and reject a run unless the response contains every expected value.

Run at least five independent invocations per model. Measure wall-clock time around the complete Hermes invocation, not only provider-reported generation time. The end-to-end result includes process startup, configuration loading, image attachment/upload, authentication, network, provider queueing, model inference, and response parsing.

Capture for every run:

- elapsed wall-clock seconds;
- process/API exit status;
- image-grounding verification pass/fail;
- timeout or retry status;
- model/provider/reasoning setting.

Report the complete run list, median, mean, minimum, maximum, and the largest tail spike. With a small sample, do not pretend p95 is precise; show the raw values instead. If a cold-start run is analyzed separately, show it rather than deleting it.

### 3. Benchmark the action leg separately

Only use a controlled, disposable, non-destructive fixture. The action test should measure:

- correct element/coordinate selection;
- input dispatch success;
- capture-after state verification;
- retries and escalations;
- wrong-action rate;
- total time to verified state.

Follow the Computer Use skill's capture → action → fresh verification ladder. Never click permissions, password fields, payment controls, 2FA, or personal applications merely to obtain a benchmark. If the task would alter the user's environment, stop and use a mock or sandbox fixture.

### 4. Interpret for routing

Use the workload's risk profile:

- **Frequent low-risk observation:** prioritize typical perception latency.
- **Sensitive or irreversible action:** prioritize action accuracy and tail stability over a small median-speed advantage.
- **Ambiguous visual state:** escalate to the stronger reasoning model before acting.
- **Unresponsive primary:** enforce a hard timeout and invoke a tested fallback.

A practical routing pattern is `fast vision primary → confidence/timeout gate → reasoning-model fallback → action → capture-after verification`. Do not claim the fallback is safer until its action leg has been tested; a higher general vision score is not proof of better GUI grounding.

## Reporting template

Use the template in `references/vision-model-benchmarking.md`. Include a short verdict that distinguishes:

- fastest typical model;
- most stable model;
- best model for sensitive actions;
- what was not tested, especially click accuracy or full action replay.

## Common traps

- Treating an external benchmark's "average speed" as Hermes end-to-end latency.
- Comparing models evaluated on different benchmark generations or task sets.
- Reporting only a median and hiding a timeout-scale outlier.
- Calling a screenshot-only test a full Computer Use test.
- Letting one model use a different prompt, image size, provider, reasoning effort, or warm/cold state.
- Inferring screen grounding from OCR or general multimodal scores.
- Repeating a click after an unverifiable result without taking a fresh capture.
- Testing on the user's live desktop when a controlled fixture would answer the question safely.
