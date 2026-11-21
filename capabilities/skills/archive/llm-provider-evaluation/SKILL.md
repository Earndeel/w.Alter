---
name: llm-provider-evaluation
description: Use for LLM routing, benchmarking, and verification.
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [llm, providers, routing, benchmarking, verification, mcp]
---

# LLM Provider Evaluation

Use this class-level skill for provider onboarding, route verification, model benchmarking, MCP/provider diagnostics, and claims about model behavior. Distinguish catalog labels, authentication, routing, entitlement, and observed behavior.

## Always-on rules

- Resolve the exact provider, endpoint, API mode, model ID, account, credential scope, and billing path before testing.
- Treat a model catalog entry, local credential, provider login, Hermes config, route label, and successful inference as separate gates.
- Run a minimal authenticated smoke test first, then verify the persisted request/billing metadata to prove which provider and model handled it.
- Never print keys, auth files, cookies, or bearer tokens; neutralize process-scoped credentials rather than changing global environment state.
- Do not call a model “uncensored,” “free,” “available,” or “working” from a label or README; use a live probe against the exact artifact and intended use.

## Routing verification

Check provider, base URL, API mode/transport, model default, inherited profile fields, and plugin/provider enablement explicitly. Cloned profiles can retain stale endpoint fields that override a requested provider. A CLI banner or model list is not routing proof; require request/session metadata or an end-to-end Hermes result.

For a provider-specific failure, classify authentication, entitlement, transport, schema, rate limit, timeout, and harness failures separately. Direct CLI success is not Hermes success, and an alternate harness rerun must retain its own timing, token, and reliability record.

## Fair benchmarking

1. Use isolated empty workspaces and one profile/runtime per candidate.
2. Normalize prompt, starting files, toolsets, permissions, reasoning level, iteration cap, and timeout.
3. Run a tiny route smoke test before the paid build.
4. Launch comparable candidates concurrently when appropriate and record start/finish timestamps, wall time, tool calls, tokens, completion state, and provider errors.
5. Independently inspect required files, install dependencies, build, run tests, launch the artifact, exercise core behavior, and perform visual QA when relevant.
6. Grade quality and reliability separately; provider-aborted runs are DNF, not model-quality evidence.
7. Fetch current prices at report time. Show conservative cost and clearly labeled cache-adjusted estimates only when the cache rate is documented.

Do not compare failed-run timings, notification arrival times, screenshots without interaction, or outputs built by different harnesses as if they were like-for-like.

## Provider/model behavior probes

Use the intended sensitive prompt for model behavior claims, without contaminating the probe with session persona or hidden system instructions when the question is the base model. Repeat the same probe across providers to distinguish weights, serving wrapper, and session prompt effects. A partial answer with refusal is not proof of a fully unrestricted model.

For MCP/provider integrations, verify discovery, schema, auth, request route, tool execution, timeout/cancellation, and error propagation. A server being listed or initialized is not proof that a real tool call works.

## Completion contract

A provider evaluation is complete only when the exact route is verified, the intended test actually ran, results are reproducible enough for the claim, costs and failures are reported honestly, and unknown entitlement or billing gates remain explicit.
