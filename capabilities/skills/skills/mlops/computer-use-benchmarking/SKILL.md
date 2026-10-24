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

## Audit an orchestrator plus decision-model browser run

1. Freeze the execution boundary before calculating metrics. Identify the first task event and the final execution response; exclude subsequent audit turns. Separate setup, browser execution, interruptions and automatic review. Report elapsed time and recorded active time separately.
2. Locate runtime logs with `rg --files /root/.codex/sessions /root/.hermes/integrations/codex/sessions`. Inspect the JSONL event types and payload keys before extracting counters: different runtimes can expose different schemas. Deduplicate mirrored logs by session ID. For cumulative token counters, take the final in-scope value or the difference between boundary values; never sum cumulative snapshots. Report input, cached input, uncached input and output separately, with `input = cached + uncached`. State the definition of a request count.
3. Aggregate decision-worker logs separately: number of calls, recorded cost, median and p95 latency, errors, retries and fallbacks. Include failed attempts in execution cost. Keep final retained answers separate when measuring answer quality. Do not equate cheap worker calls with lower total orchestration cost.
4. Verify the actual perception path by inspecting request construction. Distinguish DOM text, OCR text and image inputs. A screenshot captured for the orchestrator does not prove that the decision worker received it. If images were absent, describe the integration as text/OCR-driven; do not infer that the selected model lacks image support.
5. Inspect the decision interface's context contract. For the implementation encountered here, use `walter path router` to resolve the module, then inspect `serve/intent.py` with `rg -n '2000|context|truncate' <resolved-router-root>/serve/intent.py`. Reconstruct each request using its original question, choices and notes, then compare the question's position with the actual truncation boundary. This interface truncated context to 2,000 characters: putting course notes first could remove the question. Place the question and choices before bounded supporting notes. Verify retained final attempts separately before attributing final errors to truncation.
6. Measure browser outcome independently of quiz scores. Record successful actions, recovery attempts, human or large-model interventions, and the final application status. Passing quizzes does not establish that the platform marked the overall course complete.
7. Label conclusions as observations or comparisons. Without a matched baseline using the same task, initial authentication state and completion criteria, report relative savings and speedup as unproven. Preserve a machine-readable metrics artifact and a concise report stating scope, counting rules and missing measurements. Keep credentials, cookies and raw private content out of both.
