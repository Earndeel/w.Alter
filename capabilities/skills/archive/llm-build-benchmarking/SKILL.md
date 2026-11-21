---
name: llm-build-benchmarking
description: Run fair, evidence-backed comparisons of autonomous coding models across isolated workspaces, providers, reasoning levels, and agent harnesses.
version: 1.0.0
metadata:
  hermes:
    tags: [benchmarking, coding-agents, model-comparison, verification]
---

# LLM Build Benchmarking

## Trigger

Use when comparing two or more models, reasoning levels, providers, or autonomous coding harnesses on the same build task.

## Core contract

A benchmark result requires a working artifact backed by independent execution. Candidate prose such as “built and verified” is not evidence.

## Workflow

1. Create one empty Git repository and one isolated runtime/profile per candidate.
2. Normalize prompt, starting files, toolsets, iteration cap, permissions, and timeout.
3. Configure each model and reasoning level explicitly.
4. Run a tiny route smoke test before the paid build.
5. Verify the actual provider/model from persisted billing or request metadata; labels are not routing proof.
6. Reset candidate workspaces to equally empty states after smoke tests or failed starts.
7. Launch candidates concurrently and record wall time, tool calls, token usage, completion state, and provider errors.
8. Independently inspect required files, run dependency installation/build/tests, launch the artifact, exercise core behavior, and visually inspect it when relevant.
9. Grade quality and reliability separately. A provider-aborted run is DNF, not proof that the model would produce worse code.

## Required report dimensions

- Exact model, provider, reasoning level, and harness
- Route verification evidence
- Wall-clock duration and completion status
- Input, cached-input, output, and total tokens; never collapse cache into an unexplained total
- Tool-call count when available
- Build/test outcome
- Runtime and visual QA outcome
- Missing files or broken dependency references
- Quality verdict and reliability verdict
- Current provider prices, conservative cost, and cache-adjusted cost when the cache rate is documented

## Cost and speed accounting

Fetch current provider pricing at report time. Calculate:

`cost = input_tokens × input_rate / 1M + output_tokens × output_rate / 1M`

When cached input is reported but the reseller's cache discount is not confirmed, publish two figures: (1) conservative cost with all input at full rate; (2) a clearly labelled cache-adjusted estimate using the documented cache rate. Never present an assumed cache discount as actual billing.

Only compare wall-clock speed when both start and finish timestamps were captured for the same phase. Do not reuse the duration of a failed run for a later successful rerun, and do not infer runtime from notification arrival. Harness changes can materially alter prompt size, caching, tool cadence, and latency; report those as operational comparisons rather than pure model speed.

## Pitfalls

- Profile clones can retain stale top-level endpoint fields that override the intended provider.
- A successful one-line smoke test does not prove long-stream stability.
- High-reasoning calls may need a larger stream-idle timeout.
- Never include failed routing attempts in candidate timing.
- Do not compare screenshots alone; exercise the implementation.
- An HTML shell referencing a missing script is incomplete, regardless of how polished the shell looks.

## Provider-specific references

See `references/kie-gpt56-hermes-codex.md` for isolated Hermes-profile routing checks and a direct Codex CLI fallback harness for Kie GPT-5.6.